"""Context budget unit tests."""

from __future__ import annotations

from lesspaper_ngl.ai.profiles import (
    CONTEXT_SAFETY_MARGIN,
    PROFILE_PRESETS,
    compute_budget,
    effective_context_window,
)


def test_compute_budget_subtracts_reserved_tokens_and_safety_margin() -> None:
    budget = compute_budget(
        max_context=8000,
        system=500,
        conversation=1000,
        response_reserve=1000,
    )
    assert budget.max_context == 8000
    assert budget.system == 500
    assert budget.conversation == 1000
    assert budget.response_reserve == 1000
    assert budget.safety_margin == CONTEXT_SAFETY_MARGIN
    assert budget.rag_budget == 8000 - 500 - 1000 - 1000 - CONTEXT_SAFETY_MARGIN


def test_compute_budget_never_negative() -> None:
    budget = compute_budget(
        max_context=1000,
        system=400,
        conversation=400,
        response_reserve=400,
    )
    assert budget.rag_budget == 0


def test_effective_context_window_caps_to_provider() -> None:
    assert effective_context_window(16_000, 8_192) == 8_192
    assert effective_context_window(8_000, 32_000) == 8_000
    assert effective_context_window(8_000, None) == 8_000
    assert effective_context_window(8_000, 0) == 8_000


def test_profile_output_presets_allow_complete_answers() -> None:
    # Raised so Ask lists/explanations are less likely to hit finish_reason=length.
    assert PROFILE_PRESETS["lightweight"]["max_output_tokens"] == 2_048
    assert PROFILE_PRESETS["balanced"]["max_output_tokens"] == 3_072
    assert PROFILE_PRESETS["quality"]["max_output_tokens"] == 4_096
