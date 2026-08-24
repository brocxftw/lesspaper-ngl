"""Reciprocal rank fusion unit tests."""

from __future__ import annotations

import uuid

from lesspaper_ngl.search.hybrid import reciprocal_rank_fusion


def test_rrf_merges_ranked_lists() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    list_one = [a, b, c]
    list_two = [b, c, a]

    merged = reciprocal_rank_fusion([list_one, list_two], rrf_k=60)
    scores = dict(merged)

    assert set(scores) == {a, b, c}
    assert scores[b] > scores[c]
    assert merged[0][0] in {a, b}


def test_rrf_single_list_preserves_order() -> None:
    ids = [uuid.uuid4() for _ in range(3)]
    merged = reciprocal_rank_fusion([ids])
    assert [item_id for item_id, _ in merged] == ids
