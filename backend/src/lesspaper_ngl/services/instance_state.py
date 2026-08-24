"""Instance lifecycle state stored in app_settings."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import AppSetting, InstanceState

INSTANCE_STATE_KEY = "instance_state"
INSTALLATION_ID_KEY = "installation_id"


async def get_instance_state(session: AsyncSession) -> InstanceState:
    row = await session.get(AppSetting, INSTANCE_STATE_KEY)
    if row is None:
        return InstanceState.UNINITIALISED
    raw = row.value.get("state") if isinstance(row.value, dict) else None
    try:
        return InstanceState(str(raw))
    except ValueError:
        return InstanceState.UNINITIALISED


async def set_instance_state(session: AsyncSession, state: InstanceState) -> None:
    row = await session.get(AppSetting, INSTANCE_STATE_KEY)
    value: dict[str, Any] = {"state": state.value}
    if row is None:
        session.add(AppSetting(key=INSTANCE_STATE_KEY, value=value))
    else:
        row.value = value


async def ensure_installation_id(session: AsyncSession) -> str:
    row = await session.get(AppSetting, INSTALLATION_ID_KEY)
    if row is not None and isinstance(row.value, dict) and row.value.get("id"):
        return str(row.value["id"])
    new_id = str(uuid.uuid4())
    session.add(AppSetting(key=INSTALLATION_ID_KEY, value={"id": new_id}))
    return new_id


async def get_installation_id(session: AsyncSession) -> str | None:
    row = await session.get(AppSetting, INSTALLATION_ID_KEY)
    if row is None or not isinstance(row.value, dict):
        return None
    raw = row.value.get("id")
    return str(raw) if raw else None


async def is_uninitialised(session: AsyncSession) -> bool:
    return await get_instance_state(session) == InstanceState.UNINITIALISED
