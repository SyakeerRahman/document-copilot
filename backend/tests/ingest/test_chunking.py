from ingest import chunking
from ingest.chunking import COVER_SECTION, build_document, item_heading
from ingest.filing_html import Block, Filing, Page


def filing(*pages: list[Block]) -> Filing:
    return Filing(
        registrant_name="Example Corp",
        fiscal_year=2025,
        pages=[Page(number=i + 1, label=str(i), blocks=blocks) for i, blocks in enumerate(pages)],
    )


def text(value: str) -> Block:
    return Block("text", value)


def heading(value: str) -> Block:
    return Block("heading", value)


def test_item_heading_accepts_text_and_amazon_style_single_row_tables():
    assert item_heading(heading("Item 1A. Risk Factors")) == ("1A", "Risk Factors")
    assert item_heading(heading("ITEM 7. MANAGEMENT'S DISCUSSION")) == ("7", "MANAGEMENT'S DISCUSSION")
    assert item_heading(Block("table", "Item 7. | Management's Discussion")) == ("7", "Management's Discussion")
    assert item_heading(Block("table", "Item 1. | Business\nItem 1A. | Risk Factors")) is None  # table of contents
    assert item_heading(text("Items 1 and 2 describe the business in general terms.")) is None


def test_every_chunk_is_an_exact_slice_of_the_markdown():
    document = build_document(
        filing(
            [text("Cover page text.")],
            [heading("Item 7. MD&A"), heading("Net Sales"), text("Net sales rose."), Block("table", "A | 1\nB | 2")],
        ),
        "Example Corp Form 10-K for fiscal year 2025",
    )
    assert document.markdown.startswith("# Example Corp Form 10-K for fiscal year 2025\n\n<!-- page 1 label=0 -->")
    for chunk in document.chunks:
        assert document.markdown[chunk.char_start : chunk.char_end] == chunk.content


def test_chunks_carry_section_subsection_and_page_and_never_cross_pages():
    document = build_document(
        filing(
            [text("Cover page text.")],
            [heading("Item 7. MD&A"), heading("Net Sales"), text("Net sales rose.")],
            [text("Continued on the next page.")],
        ),
        "t",
    )
    located = [(c.page_number, c.page_label, c.section, c.subsection, c.content) for c in document.chunks]
    assert located == [
        (1, "0", COVER_SECTION, None, "Cover page text."),
        (2, "1", "Item 7. MD&A", "Net Sales", "## Item 7. MD&A\n\n### Net Sales\n\nNet sales rose."),
        (3, "2", "Item 7. MD&A", "Net Sales", "Continued on the next page."),
    ]


def test_several_short_items_on_one_page_each_get_their_own_section():
    document = build_document(
        filing(
            [heading("Item 1B. Unresolved Staff Comments"), text("None."), heading("Item 2. Properties"), text("HQ.")]
        ),
        "t",
    )
    assert [(c.section, c.content) for c in document.chunks] == [
        ("Item 1B. Unresolved Staff Comments", "## Item 1B. Unresolved Staff Comments\n\nNone."),
        ("Item 2. Properties", "## Item 2. Properties\n\nHQ."),
    ]


def test_bare_item_reference_keeps_the_title_seen_earlier():
    document = build_document(
        filing([heading("Item 7. MD&A"), text("First.")], [heading("Item 7"), text("Second.")]),
        "t",
    )
    assert {c.section for c in document.chunks} == {"Item 7. MD&A"}


def test_heading_with_no_body_is_not_a_chunk():
    document = build_document(filing([text("Body."), heading("PART II")], [text("Next page.")]), "t")
    assert [c.content for c in document.chunks] == ["Body.", "Next page."]


def test_oversized_blocks_split_at_line_breaks_within_max_chars(monkeypatch):
    monkeypatch.setattr(chunking, "MAX_CHARS", 50)
    monkeypatch.setattr(chunking, "TARGET_CHARS", 40)
    rows = "\n".join(f"Row {i} | {i * 1000:,}" for i in range(12))
    document = build_document(filing([Block("table", rows)]), "t")

    assert len(document.chunks) > 1
    assert all(len(c.content) <= 50 for c in document.chunks)
    assert all(document.markdown[c.char_start : c.char_end] == c.content for c in document.chunks)
    assert "\n".join(c.content for c in document.chunks) == rows
