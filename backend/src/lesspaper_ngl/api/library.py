"""Library overview and activity counter endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import LibraryActivityOut, LibraryOverviewOut, TagOut
from lesspaper_ngl.auth.deps import CurrentUser, SafeSession
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.services import library_stats

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/overview", response_model=LibraryOverviewOut)
async def library_overview(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryOverviewOut:
    data = await library_stats.get_overview(db, _user.id)
    return LibraryOverviewOut(
        activity=LibraryActivityOut.model_validate(data["activity"]),
        snapshot=data["snapshot"],
        file_types=data["file_types"],
        health=data["health"],
        tags=[TagOut.model_validate(tag) for tag in data["tags"]],
    )


@router.post("/reset-statistics", response_model=LibraryActivityOut)
async def reset_library_statistics(
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryActivityOut:
    await library_stats.reset_counters(db, _user.id)
    activity = await library_stats.get_activity(db, _user.id)
    return LibraryActivityOut.model_validate(activity)
