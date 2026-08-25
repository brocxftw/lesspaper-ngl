"""Aggregate API router."""

from __future__ import annotations

from fastapi import APIRouter

from lesspaper_ngl.api import (
    about,
    ai,
    ask,
    auth,
    backups,
    bootstrap,
    documents,
    folders,
    health,
    inbox,
    jobs,
    library,
    logs,
    onboarding,
    search,
    system,
    tags,
    trash,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(bootstrap.router)
api_router.include_router(onboarding.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(folders.router)
api_router.include_router(tags.router)
api_router.include_router(documents.router)
api_router.include_router(inbox.router)
api_router.include_router(library.router)
api_router.include_router(trash.router)
api_router.include_router(search.router)
api_router.include_router(ask.router)
api_router.include_router(jobs.router)
api_router.include_router(ai.router)
api_router.include_router(system.router)
api_router.include_router(backups.router)
api_router.include_router(logs.router)
api_router.include_router(about.router)
