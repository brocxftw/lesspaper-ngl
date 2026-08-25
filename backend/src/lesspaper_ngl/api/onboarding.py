"""Authenticated, per-user welcome-tour state."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import OnboardingStatusOut
from lesspaper_ngl.auth.deps import CurrentUser, SafeSession
from lesspaper_ngl.db.session import get_db

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
CURRENT_ONBOARDING_VERSION = 1


@router.get("/status", response_model=OnboardingStatusOut)
async def status(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OnboardingStatusOut:
    del db
    return OnboardingStatusOut(
        required=_user.onboarding_version < CURRENT_ONBOARDING_VERSION,
        current_version=CURRENT_ONBOARDING_VERSION,
        completed_version=_user.onboarding_version,
    )


@router.post("/complete", response_model=OnboardingStatusOut)
async def complete(
    _session: SafeSession,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OnboardingStatusOut:
    user.onboarding_version = CURRENT_ONBOARDING_VERSION
    await db.flush()
    return OnboardingStatusOut(
        required=False,
        current_version=CURRENT_ONBOARDING_VERSION,
        completed_version=user.onboarding_version,
    )
