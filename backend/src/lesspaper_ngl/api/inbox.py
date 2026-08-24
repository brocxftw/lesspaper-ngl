"""Inbox overview metrics and activity endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import InboxActivityListOut, InboxOverviewOut
from lesspaper_ngl.auth.deps import CurrentUser
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.services import inbox_overview as overview_service

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


def _parse_range_days(range_days: int) -> Literal[7, 30]:
    if range_days == 7:
        return 7
    if range_days == 30:
        return 30
    raise HTTPException(
        status_code=422,
        detail=[{"type": "literal_error", "loc": ["query", "range_days"], "msg": "Input should be 7 or 30"}],
    )


@router.get("/overview", response_model=InboxOverviewOut)
async def inbox_overview(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    range_days: Annotated[int, Query()] = 7,
) -> InboxOverviewOut:
    days = _parse_range_days(range_days)
    data = await overview_service.get_overview_metrics(
        db, owner_id=_user.id, range_days=days
    )
    return InboxOverviewOut.model_validate(data)


@router.get("/activity", response_model=InboxActivityListOut)
async def inbox_activity(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    range_days: Annotated[int, Query()] = 7,
    tab: Literal["recent", "processed", "failed"] = Query(default="recent"),
    q: str | None = Query(default=None),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> InboxActivityListOut:
    days = _parse_range_days(range_days)
    items, total = await overview_service.list_activity(
        db,
        owner_id=_user.id,
        range_days=days,
        tab=tab,
        q=q,
        page=page,
        page_size=page_size,
    )
    return InboxActivityListOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        range_days=days,
        tab=tab,
    )
