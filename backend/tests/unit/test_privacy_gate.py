"""PrivacyGate unit tests."""

from __future__ import annotations

import uuid

import pytest

from lesspaper_ngl.ai.privacy import PrivacyGate
from lesspaper_ngl.core.exceptions import PrivacyViolationError
from lesspaper_ngl.models import AIProvider, AISettings, PrivacyMode, ProviderKind


def _provider(*, is_local: bool) -> AIProvider:
    return AIProvider(
        id=uuid.uuid4(),
        name="test-provider",
        kind=ProviderKind.OPENAI_COMPATIBLE,
        base_url="http://example.com",
        is_local=is_local,
    )


def _settings(**overrides: object) -> AISettings:
    defaults = {
        "privacy_mode": PrivacyMode.LOCAL_ONLY,
        "allow_remote_embeddings": False,
        "allow_remote_qa": False,
        "allow_remote_vision": False,
        "block_remote_ai": False,
    }
    defaults.update(overrides)
    return AISettings(id=1, **defaults)  # type: ignore[arg-type]


def test_local_only_allows_local_provider() -> None:
    gate = PrivacyGate(_settings(), _provider(is_local=True))
    gate.assert_can_qa()
    gate.assert_can_embed()


def test_local_only_blocks_remote_qa() -> None:
    gate = PrivacyGate(_settings(), _provider(is_local=False))
    with pytest.raises(PrivacyViolationError):
        gate.assert_can_qa()


def test_private_hybrid_requires_allow_flag() -> None:
    gate = PrivacyGate(
        _settings(privacy_mode=PrivacyMode.PRIVATE_HYBRID, allow_remote_qa=False),
        _provider(is_local=False),
    )
    with pytest.raises(PrivacyViolationError):
        gate.assert_can_qa()

    gate_allowed = PrivacyGate(
        _settings(privacy_mode=PrivacyMode.PRIVATE_HYBRID, allow_remote_qa=True),
        _provider(is_local=False),
    )
    gate_allowed.assert_can_qa()


def test_standard_mode_respects_block_remote_ai() -> None:
    gate = PrivacyGate(
        _settings(
            privacy_mode=PrivacyMode.STANDARD,
            allow_remote_qa=True,
            block_remote_ai=True,
        ),
        _provider(is_local=False),
    )
    with pytest.raises(PrivacyViolationError):
        gate.assert_can_qa()
