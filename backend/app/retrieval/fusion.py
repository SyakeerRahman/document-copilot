from collections.abc import Hashable, Sequence

# The constant from the original RRF paper (Cormack et al., 2009). Larger k flattens the advantage of the top ranks.
RRF_K = 60


def reciprocal_rank_fusion[Key: Hashable](*rankings: Sequence[Key], k: int = RRF_K) -> list[tuple[Key, float]]:
    """Fuse ranked lists by summing 1 / (k + rank). Ties keep first-seen order, so the result is deterministic."""
    scores: dict[Key, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
