"""Privacy enforcement for AI operations."""

from __future__ import annotations

from lesspaper_ngl.core.exceptions import PrivacyViolationError
from lesspaper_ngl.models import AIProvider, AISettings, PrivacyMode


class PrivacyGate:
    """Enforce lesspaper-ngl privacy policy before sending document content to a provider."""

    def __init__(self, settings: AISettings, provider: AIProvider) -> None:
        self.settings = settings
        self.provider = provider

    def _reject_remote(self, operation: str) -> None:
        location = "local" if self.provider.is_local else "remote"
        raise PrivacyViolationError(
            f"{operation} is blocked: privacy mode {self.settings.privacy_mode.value} "
            f"does not allow sending document content to {location} provider "
            f"'{self.provider.name}'."
        )

    def _assert_remote_allowed(self, *, operation: str, allow_flag: bool) -> None:
        if self.provider.is_local:
            return

        mode = self.settings.privacy_mode

        if mode == PrivacyMode.LOCAL_ONLY:
            self._reject_remote(operation)

        if mode == PrivacyMode.PRIVATE_HYBRID:
            if not allow_flag:
                raise PrivacyViolationError(
                    f"{operation} requires allow_remote_{operation} to be enabled "
                    f"for remote provider '{self.provider.name}'."
                )
            return

        if mode == PrivacyMode.STANDARD:
            if self.settings.block_remote_ai:
                self._reject_remote(operation)
            if not allow_flag:
                raise PrivacyViolationError(
                    f"{operation} is blocked for remote provider '{self.provider.name}'."
                )

    def assert_can_embed(self) -> None:
        self._assert_remote_allowed(operation="embeddings", allow_flag=self.settings.allow_remote_embeddings)

    def assert_can_qa(self) -> None:
        self._assert_remote_allowed(operation="qa", allow_flag=self.settings.allow_remote_qa)

    def assert_can_vision(self) -> None:
        self._assert_remote_allowed(operation="vision", allow_flag=self.settings.allow_remote_vision)
