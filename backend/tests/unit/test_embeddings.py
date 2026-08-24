"""Tests for embedding storage padding."""

from __future__ import annotations

import pytest

from lesspaper_ngl.ai.embeddings import EMBEDDING_STORAGE_DIM, pad_embedding


def test_pad_embedding_extends_with_zeros() -> None:
    padded = pad_embedding([1.0, 2.0, 3.0], storage_dim=5)
    assert padded == [1.0, 2.0, 3.0, 0.0, 0.0]


def test_pad_embedding_noop_when_exact() -> None:
    values = [0.1] * EMBEDDING_STORAGE_DIM
    assert pad_embedding(values) == values


def test_pad_embedding_rejects_oversized() -> None:
    with pytest.raises(ValueError, match="exceeds storage size"):
        pad_embedding([0.0] * (EMBEDDING_STORAGE_DIM + 1))
