from ingest.filing_html import merge_table_cells, parse_filing

PAGE_BREAK = '<hr style="page-break-after:always"/>'


def filing_html(*pages: str) -> str:
    header = (
        '<div style="display:none"><ix:header>'
        '<ix:nonNumeric name="dei:DocumentFiscalYearFocus">2025</ix:nonNumeric>'
        "hidden xbrl facts</ix:header></div>"
    )
    return f"<html><body>{header}{PAGE_BREAK.join(pages)}</body></html>"


def test_pages_split_on_page_breaks_and_footer_becomes_label():
    html = filing_html(
        "<div>Cover text for <ix:nonNumeric name='dei:EntityRegistrantName'>Apple Inc.</ix:nonNumeric></div>",
        "<div>Body on page two.</div><div>Apple Inc. | 2025 Form 10-K | 1</div>",
        "<div>Body on page three.</div><div>2.</div>",
    )
    filing = parse_filing(html)

    assert filing.registrant_name == "Apple Inc."
    assert filing.fiscal_year == 2025
    assert [(page.number, page.label) for page in filing.pages] == [(1, None), (2, "1"), (3, "2")]
    assert [block.text for block in filing.pages[1].blocks] == ["Body on page two."]
    assert all("hidden xbrl" not in block.text for page in filing.pages for block in page.blocks)


def test_long_last_paragraph_is_not_mistaken_for_a_footer():
    # Ends in a number like a footer does, but is far too long to be one.
    sentence = "Revenue grew in every segment during the year and gross margin expanded compared to 2024 by 3"
    filing = parse_filing(filing_html(f"<div>{sentence}</div>"))
    assert filing.pages[0].label is None
    assert len(filing.pages[0].blocks) == 1


def test_running_headers_are_removed_from_the_top_of_pages():
    filing = parse_filing(
        filing_html("<div>PART II</div><div>Item 7</div><div>Industry trends text.</div><div>40</div>")
    )
    assert [block.text for block in filing.pages[0].blocks] == ["Industry trends text."]


def test_one_row_table_running_header_is_removed():
    header = "<table><tr><td>Table of Contents</td><td>Alphabet Inc.</td></tr></table>"
    filing = parse_filing(filing_html(f"{header}<div>Revenue discussion.</div><div>41</div>"))
    assert [block.text for block in filing.pages[0].blocks] == ["Revenue discussion."]


def test_bold_short_blocks_are_headings():
    filing = parse_filing(
        filing_html(
            '<div><span style="font-weight:700">Item 1A.&#160;&#160;Risk Factors</span></div>'
            "<div><b>Macroeconomic</b> conditions matter.</div>"
        )
    )
    kinds = [(block.kind, block.text) for block in filing.pages[0].blocks]
    assert kinds == [("heading", "Item 1A. Risk Factors"), ("text", "Macroeconomic conditions matter.")]


def test_tables_become_pipe_rows_with_currency_and_percent_cells_merged():
    table = (
        "<table>"
        "<tr><td></td><td>2025</td><td></td><td>Change</td></tr>"
        "<tr><td>Americas</td><td>$</td><td>178,353</td><td>7</td><td>%</td></tr>"
        "<tr><td>Greater China</td><td></td><td>64,377</td><td>(4</td><td>)%</td></tr>"
        "<tr><td></td><td></td></tr>"
        "</table>"
    )
    filing = parse_filing(filing_html(f"<div>The following table shows net sales:</div>{table}"))
    blocks = filing.pages[0].blocks
    assert blocks[1].kind == "table"
    assert blocks[1].text == "2025 | Change\nAmericas | $178,353 | 7%\nGreater China | 64,377 | (4)%"


def test_merge_table_cells_keeps_trailing_prefix():
    assert merge_table_cells(["Total", "$"]) == ["Total", "$"]
