import pytest

from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.queries import keyword_tsquery


def test_item_found_by_both_methods_beats_item_ranked_first_by_one():
    fused = reciprocal_rank_fusion(["a", "b", "c"], ["b", "d"], k=60)
    assert [key for key, _ in fused] == ["b", "a", "d", "c"]
    assert fused[0][1] == pytest.approx(1 / 62 + 1 / 61)


def test_one_empty_ranking_keeps_the_other_order():
    assert [key for key, _ in reciprocal_rank_fusion(["x", "y", "z"], [])] == ["x", "y", "z"]


def test_ties_keep_first_seen_order():
    assert [key for key, _ in reciprocal_rank_fusion(["a"], ["b"])] == ["a", "b"]


def test_keyword_query_ors_unique_words_and_drops_syntax():
    assert (
        keyword_tsquery("AWS operating income: AWS vs. North-America?")
        == "aws | operating | income | vs | north | america"
    )


@pytest.mark.parametrize("question", ["' | !:* & ( )", "", "   "])
def test_keyword_query_from_punctuation_only_is_empty(question):
    assert keyword_tsquery(question) == ""
