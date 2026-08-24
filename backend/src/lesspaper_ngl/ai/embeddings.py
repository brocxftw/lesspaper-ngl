"""Helpers for storing variable-length embeddings in a fixed pgvector column."""

from __future__ import annotations

# Matches DocumentChunk.embedding = Vector(3072) and alembic 001_initial.
EMBEDDING_STORAGE_DIM = 3072


def pad_embedding(
    values: list[float],
    *,
    storage_dim: int = EMBEDDING_STORAGE_DIM,
) -> list[float]:
    """Pad or reject an embedding so it fits the fixed Vector(storage_dim) column.

    Trailing zeros preserve cosine similarity when both query and document
    vectors are padded the same way.
    """
    if storage_dim <= 0:
        raise ValueError("storage_dim must be positive")
    if len(values) == storage_dim:
        return list(values)
    if len(values) > storage_dim:
        raise ValueError(
            f"Embedding dimension {len(values)} exceeds storage size {storage_dim}"
        )
    padded = list(values)
    padded.extend([0.0] * (storage_dim - len(values)))
    return padded
