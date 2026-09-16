"""Turn a parsed filing into normalized Markdown and retrieval chunks.

Chunks never cross a page or a section boundary, so each one cites exactly one page. Every chunk's
`content` is an exact slice of the document Markdown (`markdown[char_start:char_end]`), which is
what `source_documents.content_markdown` stores, so a citation can always be traced back verbatim.
"""

import re
from dataclasses import dataclass

from ingest.filing_html import HEADING_MAX_CHARS, Block, Filing

TARGET_CHARS = 1800
MAX_CHARS = 3000
# Every table of contents in the corpus is a multi-row table, which item_heading ignores, so
# several Item headings on one page are real: short Items like 1B-4 often share a page.
COVER_SECTION = "Cover page"

ITEM_HEADING = re.compile(r"^(?:part\s+[ivx]+\W+)?item\s+(\d{1,2}[a-c]?)\b\s*[.:\-]?\s*(.*)$", re.IGNORECASE)


@dataclass
class Chunk:
    index: int
    page_number: int
    page_label: str | None
    section: str
    subsection: str | None
    content: str
    char_start: int
    char_end: int


@dataclass
class Document:
    markdown: str
    chunks: list[Chunk]


@dataclass
class _Span:
    page_number: int
    page_label: str | None
    section: str
    subsection: str | None
    is_heading: bool
    start: int
    end: int


def item_heading(block: Block) -> tuple[str, str] | None:
    text = block.text
    if block.kind == "table":
        if "\n" in text:
            return None
        text = text.replace(" | ", " ")  # Amazon puts "Item 7." and its title in two cells
    if len(text) > HEADING_MAX_CHARS:
        return None
    match = ITEM_HEADING.match(text)
    if match is None:
        return None
    return match.group(1).upper(), match.group(2).strip(" .")


def build_document(filing: Filing, title: str) -> Document:
    parts: list[str] = []
    position = 0

    def emit(text: str) -> tuple[int, int]:
        nonlocal position
        start = position
        parts.append(text)
        position += len(text)
        return start, position

    emit(f"# {title}\n\n")

    spans: list[_Span] = []
    item_titles: dict[str, str] = {}
    section = COVER_SECTION
    subsection: str | None = None

    for page in filing.pages:
        emit(f"<!-- page {page.number}" + (f" label={page.label}" if page.label else "") + " -->\n\n")
        for block in page.blocks:
            heading = item_heading(block)
            if heading is not None:
                number, heading_title = heading
                if heading_title:
                    item_titles.setdefault(number, heading_title)
                title_text = item_titles.get(number)
                section = f"Item {number}. {title_text}" if title_text else f"Item {number}"
                subsection = None
                rendered, is_heading = f"## {block.text.replace(' | ', ' ')}", True
            elif block.kind == "heading":
                subsection = block.text
                rendered, is_heading = f"### {block.text}", True
            else:
                rendered, is_heading = block.text, False

            start, end = emit(rendered)
            emit("\n\n")
            spans.append(_Span(page.number, page.label, section, subsection, is_heading, start, end))

    markdown = "".join(parts)
    return Document(markdown=markdown, chunks=_group(spans, markdown))


def _group(spans: list[_Span], markdown: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    current: list[_Span] = []

    def flush() -> None:
        if all(span.is_heading for span in current):
            current.clear()  # a heading with no body (end of page) has nothing to retrieve
            return
        first, last = current[0], current[-1]
        for start, end in _split(markdown, first.start, last.end):
            chunks.append(
                Chunk(
                    index=len(chunks),
                    page_number=first.page_number,
                    page_label=first.page_label,
                    section=first.section,
                    subsection=last.subsection if last.section == first.section else first.subsection,
                    content=markdown[start:end],
                    char_start=start,
                    char_end=end,
                )
            )
        current.clear()

    for span in spans:
        if current:
            head = current[0]
            has_body = any(not s.is_heading for s in current)
            starts_new = (
                span.page_number != head.page_number
                or span.section != head.section
                or (span.is_heading and has_body)
                or span.end - head.start > TARGET_CHARS
            )
            if starts_new:
                flush()
        current.append(span)
    flush()
    return chunks


def _split(markdown: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split an over-long range at line breaks, then sentence ends, then hard at MAX_CHARS."""
    pieces = []
    while end - start > MAX_CHARS:
        window = markdown[start : start + MAX_CHARS]
        cut = max(window.rfind("\n"), window.rfind(". ") + 1)
        if cut < MAX_CHARS // 2:
            cut = MAX_CHARS
        pieces.append((start, start + cut))
        start += cut
        while start < end and markdown[start].isspace():
            start += 1
    if end > start:
        pieces.append((start, end))
    return [(s, _rstrip(markdown, s, e)) for s, e in pieces]


def _rstrip(markdown: str, start: int, end: int) -> int:
    while end > start and markdown[end - 1].isspace():
        end -= 1
    return end
