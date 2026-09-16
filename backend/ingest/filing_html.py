"""Parse an SEC 10-K primary document (inline XBRL HTML) into pages of text blocks.

The page is the citation unit, so page boundaries are kept exactly. Every filing in the corpus
marks them with `<hr style="page-break-after:always">` and prints its page number as the last
line of the page, which becomes `Page.label` instead of chunk text.
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal

BlockKind = Literal["text", "heading", "table"]

VOID_TAGS = {"br", "hr", "img", "meta", "link", "input", "col", "area", "base", "wbr"}
BLOCK_TAGS = {"div", "p", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "center"}
CELL_TAGS = {"td", "th"}

HIDDEN_STYLE = re.compile(r"display\s*:\s*none", re.IGNORECASE)
PAGE_BREAK_STYLE = re.compile(
    r"page-break-(?:after|before)\s*:\s*always|break-(?:after|before)\s*:\s*page", re.IGNORECASE
)
BOLD_STYLE = re.compile(r"font-weight\s*:\s*(?:bold|[6-9]00)", re.IGNORECASE)

HEADING_MAX_CHARS = 150
FOOTER_MAX_CHARS = 80
# "Apple Inc. | 2025 Form 10-K | 23", "23", "23.", "F-4"
FOOTER_LABEL = re.compile(r"(?:^|[|\s])([A-Z]{0,2}-?\d{1,3})\.?$")

# Cells that belong to a neighbour in financial tables: "$" | "1,234" | ")" -> "$1,234)"
PREFIX_CELLS = {"$", "(", "($", "$("}
SUFFIX_CELLS = {")", "%", ")%", "%)", "pts", "bps"}


@dataclass
class Block:
    kind: BlockKind
    text: str


@dataclass
class Page:
    number: int
    label: str | None
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Filing:
    registrant_name: str | None
    fiscal_year: int | None
    pages: list[Page]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def merge_table_cells(cells: list[str]) -> list[str]:
    merged: list[str] = []
    pending_prefix = ""
    for cell in cells:
        if cell in PREFIX_CELLS:
            pending_prefix += cell
            continue
        if cell in SUFFIX_CELLS and merged:
            merged[-1] += cell
            continue
        merged.append(pending_prefix + cell)
        pending_prefix = ""
    if pending_prefix:
        merged.append(pending_prefix)
    return merged


def render_table(rows: list[list[str]]) -> str:
    lines = []
    for row in rows:
        cells = merge_table_cells([cell for cell in row if cell])
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


class _FilingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # One entry per open non-void element: (tag, hidden, bold, page_break)
        self._stack: list[tuple[str, bool, bool, bool]] = []
        self._hidden_depth = 0
        self._bold_depth = 0

        self.pages: list[Page] = [Page(number=1, label=None)]
        self._text: list[str] = []
        self._text_all_bold = True

        self._table_depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

        self._dei_field: str | None = None
        self._dei_text: list[str] = []
        self.dei: dict[str, str] = {}

    # --- element tracking -------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = attributes.get("style") or ""
        hidden = bool(HIDDEN_STYLE.search(style))
        bold = tag in {"b", "strong"} or bool(BOLD_STYLE.search(style))
        page_break = bool(PAGE_BREAK_STYLE.search(style))

        if tag == "ix:nonnumeric" and (attributes.get("name") or "").startswith("dei:"):
            self._dei_field = attributes["name"]
            self._dei_text = []

        if tag in VOID_TAGS:
            if tag == "br":
                self._append_text(" ")
            if page_break:
                self._break_page()
            return

        if tag in BLOCK_TAGS and self._table_depth == 0:
            self._flush_text()
        if tag == "table":
            self._flush_text()
            if self._table_depth == 0:
                self._rows = []
            self._table_depth += 1
        elif tag == "tr" and self._table_depth:
            self._row = []
        elif tag in CELL_TAGS and self._table_depth:
            self._cell = []

        self._stack.append((tag, hidden, bold, page_break))
        self._hidden_depth += hidden
        self._bold_depth += bold

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID_TAGS:
            self.handle_starttag(tag, attrs)
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if not any(open_tag == tag for open_tag, *_ in self._stack):
            return  # stray closing tag
        while self._stack:
            open_tag, hidden, bold, page_break = self._stack.pop()
            self._hidden_depth -= hidden
            self._bold_depth -= bold
            self._close(open_tag, page_break)
            if open_tag == tag:
                break

    def _close(self, tag: str, page_break: bool) -> None:
        if tag == "ix:nonnumeric" and self._dei_field:
            self.dei.setdefault(self._dei_field, normalize_space("".join(self._dei_text)))
            self._dei_field = None
        if tag in CELL_TAGS and self._cell is not None and self._row is not None:
            self._row.append(normalize_space("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                rendered = render_table(self._rows)
                if rendered:
                    self._current_page.blocks.append(Block("table", rendered))
                self._rows = []
        elif tag in BLOCK_TAGS and self._table_depth == 0:
            self._flush_text()
        if page_break:
            self._break_page()

    # --- text -------------------------------------------------------------

    def handle_data(self, data: str) -> None:
        if self._dei_field is not None:
            self._dei_text.append(data)
        if self._hidden_depth:
            return
        self._append_text(data)

    def _append_text(self, data: str) -> None:
        if self._table_depth:
            if self._cell is not None:
                self._cell.append(data)
            return
        self._text.append(data)
        if data.strip() and not self._bold_depth:
            self._text_all_bold = False

    def _flush_text(self) -> None:
        text = normalize_space("".join(self._text))
        if text:
            is_heading = self._text_all_bold and len(text) <= HEADING_MAX_CHARS
            self._current_page.blocks.append(Block("heading" if is_heading else "text", text))
        self._text = []
        self._text_all_bold = True

    # --- pages ------------------------------------------------------------

    @property
    def _current_page(self) -> Page:
        return self.pages[-1]

    def _break_page(self) -> None:
        self._flush_text()
        page = self._current_page
        if not page.blocks:
            return  # consecutive breaks; do not count empty pages
        page.label = _pop_footer_label(page)
        _strip_running_headers(page)
        self.pages.append(Page(number=page.number + 1, label=None))

    def finish(self) -> None:
        self._flush_text()
        page = self._current_page
        if page.blocks:
            page.label = _pop_footer_label(page)
            _strip_running_headers(page)
        else:
            self.pages.pop()


# Repeated at the top of pages: "Table of Contents" links (Amazon), "PART II" / "Item 7" (Microsoft),
# and a one-row table "Table of Contents | Alphabet Inc." (Alphabet).
RUNNING_HEADER = re.compile(
    r"^(?:table of contents(?: \| [^|]{1,40})?|part\s+[ivx]+|item\s+\d{1,2}[a-c]?\.?)$", re.IGNORECASE
)
RUNNING_HEADER_SCAN = 3


def _strip_running_headers(page: Page) -> None:
    kept_from = 0
    for block in page.blocks[:RUNNING_HEADER_SCAN]:
        if "\n" in block.text or not RUNNING_HEADER.match(block.text):
            break
        kept_from += 1
    del page.blocks[:kept_from]


def _pop_footer_label(page: Page) -> str | None:
    last = page.blocks[-1]
    if last.kind == "table" or len(last.text) > FOOTER_MAX_CHARS:
        return None
    match = FOOTER_LABEL.search(last.text)
    if match is None:
        return None
    page.blocks.pop()
    return match.group(1)


def parse_filing(html: str) -> Filing:
    parser = _FilingParser()
    parser.feed(html)
    parser.close()
    parser.finish()

    fiscal_year = parser.dei.get("dei:DocumentFiscalYearFocus")
    return Filing(
        registrant_name=parser.dei.get("dei:EntityRegistrantName") or None,
        fiscal_year=int(fiscal_year) if fiscal_year and fiscal_year.isdigit() else None,
        pages=[page for page in parser.pages if page.blocks],
    )
