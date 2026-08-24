"""Application bootstrap: system folders, admin user, AI settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.auth import service as auth_service
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.models import AIProfileName, AISettings, InstanceState, PrivacyMode, User
from lesspaper_ngl.services import folders as folder_service
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.storage.service import StorageService


async def ensure_ai_settings(session: AsyncSession) -> AISettings:
    """Ensure the singleton AI settings row exists."""
    settings_row = await session.get(AISettings, 1)
    if settings_row is not None:
        return settings_row

    config = get_settings()
    privacy = PrivacyMode(config.ai_privacy_mode.value)
    profile = AIProfileName(config.ai_profile.value)

    settings_row = AISettings(
        id=1,
        privacy_mode=privacy,
        profile=profile,
        allow_remote_embeddings=config.ai_allow_remote_embeddings,
        allow_remote_qa=config.ai_allow_remote_qa,
        allow_remote_vision=config.ai_allow_remote_vision,
        warn_before_remote=config.ai_warn_before_remote,
    )
    session.add(settings_row)
    await session.flush()
    return settings_row


async def bootstrap(session: AsyncSession) -> None:
    """Initialize storage layout and instance state.

    On an empty database, defer admin creation until bootstrap setup or restore.
    """
    storage = StorageService()
    storage.ensure_layout()
    any_user = (await session.execute(select(User.id).limit(1))).scalar_one_or_none()
    if any_user is None:
        await instance_state_service.set_instance_state(session, InstanceState.UNINITIALISED)
        return
    admin = await auth_service.ensure_admin_user(session)
    await folder_service.ensure_system_folders(session, admin.id)
    await ensure_ai_settings(session)
    await instance_state_service.ensure_installation_id(session)
    await instance_state_service.set_instance_state(session, InstanceState.READY)
