"""Runtime-supplied product and canonical project metadata."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter

from lesspaper_ngl import __version__
from lesspaper_ngl.api.schemas import AboutOut
from lesspaper_ngl.auth.deps import CurrentUser
from lesspaper_ngl.core.config import get_settings

router = APIRouter(prefix="/api/about", tags=["about"])


@router.get("", response_model=AboutOut)
async def about(_user: CurrentUser) -> AboutOut:
    settings = get_settings()
    candidates = {
        "repository": settings.repository_url,
        "issues": settings.issues_url,
        "documentation": settings.docs_url,
        "releases": settings.releases_url,
        "license": settings.license_url,
    }
    project_links = {
        key: value
        for key, value in candidates.items()
        if value and urlparse(value).scheme in {"http", "https"}
    }
    return AboutOut(
        version=__version__,
        description=(
            "A local-first document workspace for organizing, searching, "
            "and understanding your archive."
        ),
        build_revision=settings.build_revision,
        build_date=settings.build_date,
        project_links=project_links,
    )
