"""lesspaper-ngl FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from lesspaper_ngl import __version__
from lesspaper_ngl.api.errors import register_exception_handlers
from lesspaper_ngl.api.router import api_router
from lesspaper_ngl.bootstrap import bootstrap
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.logging import request_id_context, setup_logging
from lesspaper_ngl.db.session import dispose_engine, session_scope
from lesspaper_ngl.mcp import build_mcp_asgi, mcp


class _McpProxy:
    """Stable `/mcp` mount; inner app is rebuilt each lifespan (new session manager)."""

    def __init__(self) -> None:
        self._app: ASGIApp | None = None

    def set_app(self, app: ASGIApp | None) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        inner = self._app
        if inner is None:
            response = JSONResponse({"error": "MCP unavailable"}, status_code=503)
            await response(scope, receive, send)
            return
        await inner(scope, receive, send)


_mcp_proxy = _McpProxy()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging("api")
    async with session_scope() as session:
        await bootstrap(session)

    # streamable_http_app() builds a session manager that can be .run() only once.
    _mcp_proxy.set_app(build_mcp_asgi())
    ready = asyncio.Event()
    stop = asyncio.Event()

    async def _run_mcp() -> None:
        try:
            async with mcp.session_manager.run():
                ready.set()
                await stop.wait()
        finally:
            ready.set()

    runner = asyncio.create_task(_run_mcp())
    try:
        await ready.wait()
        if runner.done():
            await runner
        yield
    finally:
        stop.set()
        await runner
        _mcp_proxy.set_app(None)
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="lesspaper-ngl",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    access_logger = logging.getLogger("lesspaper_ngl.api.access")

    @app.middleware("http")
    async def mcp_accept_no_trailing_slash(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # FastAPI Mount("/mcp") matches /mcp/... only; MCP clients POST /mcp.
        if request.scope.get("path") == "/mcp":
            request.scope["path"] = "/mcp/"
            if isinstance(request.scope.get("raw_path"), (bytes, bytearray)):
                request.scope["raw_path"] = b"/mcp/"
        return await call_next(request)

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            access_logger.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            return response
        finally:
            request_id_context.reset(token)

    register_exception_handlers(app)
    app.include_router(api_router)
    app.mount("/mcp", _mcp_proxy)

    return app


app = create_app()


def run_api() -> None:
    settings = get_settings()
    uvicorn.run(
        "lesspaper_ngl.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_dev,
    )


if __name__ == "__main__":
    run_api()
