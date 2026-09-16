from datetime import date
from uuid import uuid4

import pytest

from app.assistant.citations import PassageRegistry
from app.grounding.validator import NO_ADVICE_SENTENCE, NO_EVIDENCE_SENTENCE, check_grounding, parse_figures
from app.retrieval.models import SourcePassage

SEGMENT_TABLE = """Year Ended December 31,
2024 | 2025
North America
Operating income | $24,967 | $29,619
International
Operating income (loss) | $3,792 | $4,750
AWS
Operating income | $39,834 | $45,606
Consolidated
Operating income | $68,593 | $79,975"""

MD_AND_A = "AWS sales increased 20% in 2025, compared to the prior year. Changes in foreign exchange rates reduced AWS operating income by $341 million."


def registry_with(*contents: str) -> PassageRegistry:
    registry = PassageRegistry()
    for content in contents:
        registry.register(
            SourcePassage(
                chunk_id=uuid4(),
                document_id=uuid4(),
                chunk_index=0,
                ticker="AMZN",
                company_name="AMAZON.COM, INC.",
                filing_type="10-K",
                fiscal_year=2025,
                filing_date=date(2026, 2, 6),
                source_url="https://www.sec.gov/x",
                page_number=70,
                page_label="68",
                section="Item 8",
                subsection=None,
                content=content,
            )
        )
    return registry


def test_real_style_answer_with_table_and_labelled_calculation_is_grounded():
    answer = """AWS was the most profitable of Amazon's three segments in fiscal 2025, with operating income of $45,606 million, versus $29,619 million for North America and $4,750 million for International [P1].

| Segment | Operating income, FY2025 |
|---|---|
| AWS | $45,606 million |
| North America | $29,619 million |
| Consolidated | $79,975 million |

AWS operating income exceeded North America by $15,987 million (my calculation from the figures above) [P1]. AWS sales increased 20% in 2025, and foreign exchange reduced AWS operating income by $341 million [P2]."""

    report = check_grounding(answer, registry_with(SEGMENT_TABLE, MD_AND_A))

    assert report.violations == []
    assert report.grounded


@pytest.mark.parametrize(
    ("figure", "grounded"),
    [
        ("$45.6 billion", True),  # 45,606 in millions, rounded
        ("$4.8 billion", True),  # 4,750 rounds up to 4.8 at one decimal
        ("$4.7 billion", False),  # wrong rounding direction
        ("$45,606 million", True),
        ("$45,610 million", False),
        ("20%", True),
        ("21%", False),
        ("$341 million", True),
    ],
)
def test_numbers_must_match_a_cited_passage_allowing_rounding_and_units(figure, grounded):
    answer = f"The filing reports {figure} [P1][P2]."
    assert check_grounding(answer, registry_with(SEGMENT_TABLE, MD_AND_A)).grounded is grounded


def test_invented_figure_is_named_in_the_violation():
    report = check_grounding("AWS operating margin was 37% [P1].", registry_with(SEGMENT_TABLE))
    expected = (
        '"37%" does not appear in any passage the answer cites. Cite the passage that states it, '
        "say in the same sentence that it is your calculation, or remove it."
    )
    assert report.violations == [expected]


def test_calculation_label_covers_only_its_own_sentence():
    answer = "AWS margin was 35.4%, my calculation [P1]. International margin was 2.9% [P1]."
    report = check_grounding(answer, registry_with(SEGMENT_TABLE))
    assert [v.split('"')[1] for v in report.violations] == ["2.9%"]


def test_figure_from_an_uncited_passage_does_not_count():
    registry = registry_with(SEGMENT_TABLE, MD_AND_A)  # P2 holds the 20%, but the answer cites only P1
    report = check_grounding("AWS grew 20% [P1].", registry)
    assert not report.grounded


def test_invented_handle_is_a_violation():
    report = check_grounding("AWS earned $45,606 million [P1][P9].", registry_with(SEGMENT_TABLE))
    assert report.violations == ["[P9] was not returned by any tool in this turn."]


def test_answer_with_no_citations_must_use_a_decline_sentence():
    registry = registry_with(SEGMENT_TABLE)
    assert not check_grounding("Tesla is not in the corpus.", registry).grounded
    assert check_grounding(f"Tesla is not in the corpus. {NO_EVIDENCE_SENTENCE}", registry).grounded
    assert check_grounding(f"{NO_ADVICE_SENTENCE} Review the filings yourself.", registry).grounded


def test_decline_sentence_does_not_excuse_invented_figures():
    report = check_grounding(f"{NO_EVIDENCE_SENTENCE} Tesla earned $97 billion.", registry_with(SEGMENT_TABLE))
    assert not report.grounded


def test_references_years_and_small_counts_are_not_figures():
    text = "In fiscal 2025, Item 7 and Note 10 on page 68 of the 10-K describe the three segments across 2 years [P1]."
    assert parse_figures(text, skip_references=True) == []
    assert check_grounding(text, registry_with(SEGMENT_TABLE)).grounded


def test_small_dollar_amounts_are_still_figures():
    figures = parse_figures("It paid $3 per share.", skip_references=True)
    assert [f.text for f in figures] == ["3"]


def test_feedback_lists_every_violation_for_the_model():
    report = check_grounding("AWS margin was 37% [P4].", registry_with(SEGMENT_TABLE))
    feedback = report.feedback()
    assert feedback.startswith("Your answer failed the citation check.")
    assert "[P4] was not returned" in feedback
    assert '"37%"' in feedback


INCOME_AS_PERCENT = """The following table sets forth certain items in our Consolidated Statements of Income expressed as a percentage of revenue.

Year Ended
Jan 28, 2024 | Jan 29, 2023
Revenue | 100.0% | 100.0%
Cost of revenue | 27.3 | 43.1
Gross profit | 72.7 | 56.9"""

APPLE_CATEGORIES = """Net sales by category:
iPhone | $191,973 | $137,781
Mac | 35,190 | 28,622
Total net sales | $365,817 | $274,515"""


def test_percentage_matches_a_bare_number_in_a_table_captioned_as_percentages():
    # From a real DeepSeek answer that the first version of the validator rejected.
    answer = "As a percentage of revenue, cost of revenue fell from 43.1% in FY2023 to 27.3% in FY2024 [P1]."
    assert check_grounding(answer, registry_with(INCOME_AS_PERCENT)).grounded


def test_calculation_label_in_a_table_caption_covers_every_row():
    # From a real DeepSeek answer that the first version of the validator rejected.
    answer = """Apple's fiscal 2021 net sales were $365,817M in total [P1].

As a share of total net sales (my calculation from the figures in [P1]):

| Category | Net sales (2021) | % of total |
|---|---|---|
| iPhone | $191,973M | 52.5% |
| Mac | $35,190M | 9.6% |"""
    assert check_grounding(answer, registry_with(APPLE_CATEGORIES)).grounded


def test_table_without_a_calculation_label_is_still_checked_row_by_row():
    answer = """Apple's net sales by category [P1]:

| Category | % of total |
|---|---|
| iPhone | 52.5% |"""
    report = check_grounding(answer, registry_with(APPLE_CATEGORIES))
    assert [v.split('"')[1] for v in report.violations] == ["52.5%"]


def test_calculation_label_in_the_sentence_after_a_table_does_not_cover_it():
    answer = """| Category | % of total |
|---|---|
| iPhone | 52.5% |

These shares are my calculation [P1]."""
    assert not check_grounding(answer, registry_with(APPLE_CATEGORIES)).grounded
