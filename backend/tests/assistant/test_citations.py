from datetime import date
from uuid import uuid4

from app.assistant.citations import PassageRegistry, extract_citations, strip_citation_markers
from app.retrieval.models import SourcePassage


def passage(content: str = "text") -> SourcePassage:
    return SourcePassage(
        chunk_id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        ticker="AAPL",
        company_name="Apple Inc.",
        filing_type="10-K",
        fiscal_year=2025,
        filing_date=date(2025, 10, 31),
        source_url="https://www.sec.gov/x",
        page_number=24,
        page_label="22",
        section="Item 7",
        subsection=None,
        content=content,
    )


def test_same_chunk_keeps_its_first_handle():
    registry = PassageRegistry()
    first, second = passage(), passage()
    assert registry.register(first) == "P1"
    assert registry.register(second) == "P2"
    assert registry.register(first) == "P1"
    assert len(registry) == 2


def test_citations_resolve_in_first_appearance_order_without_repeats():
    registry = PassageRegistry()
    a, b = passage("a"), passage("b")
    registry.register(a)
    registry.register(b)

    answer = extract_citations("Services grew [P2]. iPhone fell [P1][P2]. Mac grew [P2].", registry)

    assert [(c.handle, c.passage) for c in answer.citations] == [("P2", b), ("P1", a)]
    assert answer.unknown_handles == []


def test_handle_never_shown_to_the_model_is_reported_not_resolved():
    registry = PassageRegistry()
    registry.register(passage())

    answer = extract_citations("Revenue was $1 [P1]. Margin was 40% [P7].", registry)

    assert [c.handle for c in answer.citations] == ["P1"]
    assert answer.unknown_handles == ["P7"]


def test_text_that_only_looks_like_a_citation_is_ignored():
    assert extract_citations("See Note [7] and [p1] and [P].", PassageRegistry()).unknown_handles == []


def test_history_markers_are_removed_so_old_handles_cannot_resolve_to_new_passages():
    assert strip_citation_markers("AWS grew 19% [P3][P4]. Margin rose [P1].") == "AWS grew 19%. Margin rose."
