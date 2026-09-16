"""Grounding checks for an answer, independent of any model.

An answer is grounded when:

1. every citation handle in it was returned by a tool in this turn,
2. it cites at least one passage, unless it uses one of the exact decline sentences, and
3. every number in it appears in a passage that it cites, allowing for rounding and a change of unit,
   or sits in a sentence that says the number is the model's own calculation.

Check 3 catches the failure that matters most to an analyst: a plausible figure that no filing states.
It cannot tell whether a correct figure is attached to the right claim; that is what the citations let a
person verify.
"""

import re
from dataclasses import dataclass

from app.assistant.citations import CITATION_MARKER, PassageRegistry

# The only ways an answer may cite nothing. instructions.md tells the model to use these exact sentences.
NO_EVIDENCE_SENTENCE = "The filings in the corpus do not contain enough evidence to answer this."
NO_ADVICE_SENTENCE = "I do not give investment advice."
DECLINE_SENTENCES = (NO_EVIDENCE_SENTENCE, NO_ADVICE_SENTENCE)

CALCULATION_WORDS = re.compile(r"\bcalculat|\bderived\b|\bcomputed\b", re.IGNORECASE)

SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
NUMBER = re.compile(
    r"(?<![\w.])(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<percent>\s?%)?"
    r"(?:\s?(?P<scale>thousand|million|billion|trillion)s?\b)?",
    re.IGNORECASE,
)
# Numbers that are references or labels, not figures a filing must support.
REFERENCE_CONTEXT = re.compile(
    r"(?:\[P|\bItem\s|\bNote\s|\bpage\s|\bpages\s|\bfiscal(?:\syear)?\s|\bFY|\bQ|\bForm\s|\b10-|\bPart\s)$",
    re.IGNORECASE,
)
SMALL_COUNT = 10  # "three segments", "2 filings": counts this small are wording, not figures
YEAR_RANGE = range(1990, 2101)


@dataclass(frozen=True)
class Figure:
    text: str
    value: float
    # Half of the last stated digit, at the stated scale: "4.8 billion" may stand for 4.75 to 4.85 billion.
    rounding: float
    percent: bool


@dataclass(frozen=True)
class GroundingReport:
    violations: list[str]

    @property
    def grounded(self) -> bool:
        return not self.violations

    def feedback(self) -> str:
        """What the model reads when it must revise the answer."""
        return (
            "Your answer failed the citation check. Revise it and fix every problem below. "
            "Cite only handles that a tool returned in this turn. Every number must appear in a passage you "
            "cite, or its sentence must say that it is your calculation.\n- " + "\n- ".join(self.violations)
        )


def parse_figures(text: str, *, skip_references: bool) -> list[Figure]:
    figures = []
    for match in NUMBER.finditer(text):
        raw = match.group("number")
        digits = raw.replace(",", "")
        value = float(digits)
        percent = bool(match.group("percent"))
        scale_word = (match.group("scale") or "").lower()
        if skip_references and not percent and not scale_word:
            before = text[max(0, match.start() - 12) : match.start()]
            is_money = before.rstrip().endswith("$")
            if not is_money and (
                REFERENCE_CONTEXT.search(before)
                or (value.is_integer() and int(value) in YEAR_RANGE)
                or (value.is_integer() and value <= SMALL_COUNT)
            ):
                continue
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        scale = SCALES.get(scale_word, 1.0)
        figures.append(
            Figure(
                text=match.group(0).strip(), value=value * scale, rounding=0.5 * 10**-decimals * scale, percent=percent
            )
        )
    return figures


def _rounds_to(exact: float, stated: float, half_step: float) -> bool:
    # Half-up rounding: 4,750 million is stated as 4.8 billion, never 4.7. The interval includes its lower
    # edge and excludes its upper edge. The tolerance absorbs float error only.
    tolerance = half_step * 1e-6 + 1e-9
    return stated - half_step - tolerance <= exact < stated + half_step - tolerance


def _supported(figure: Figure, passage_figures: list[Figure]) -> bool:
    for candidate in passage_figures:
        # A percentage may match a bare number: filing tables often say "expressed as a percentage of revenue"
        # once in the caption and then list "27.3" without a % sign.
        if candidate.percent and not figure.percent:
            continue
        # Filing tables state amounts "in millions" or "in thousands" without a unit next to each number.
        for unit in (1.0, 1e3, 1e6, 1e9) if not figure.percent else (1.0,):
            if _rounds_to(candidate.value * unit, figure.value, figure.rounding):
                return True
    return False


def _claims(text: str) -> list[str]:
    """Split an answer into the units that a calculation label can cover.

    Outside tables, the unit is a sentence. A Markdown table is one unit together with the line just before
    it, so a caption such as "As a share of total (my calculation):" or a header column labelled as a
    calculation covers every row.
    """
    claims: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].lstrip().startswith("|"):
            table = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table.append(lines[index])
                index += 1
            caption = claims.pop() if claims and not claims[-1].lstrip().startswith("|") else ""
            claims.append("\n".join([caption, *table]))
            continue
        claims.extend(part for part in re.split(r"(?<=[.!?])\s+", lines[index]) if part.strip())
        index += 1
    return claims


def check_grounding(text: str, registry: PassageRegistry) -> GroundingReport:
    violations: list[str] = []
    handles = list(dict.fromkeys(CITATION_MARKER.findall(text)))
    cited = [registry.get(handle) for handle in handles]
    unknown = [handle for handle, passage in zip(handles, cited, strict=True) if passage is None]
    for handle in unknown:
        violations.append(f"[{handle}] was not returned by any tool in this turn.")

    passages = [passage for passage in cited if passage is not None]
    if not passages and not any(sentence in text for sentence in DECLINE_SENTENCES):
        violations.append(
            "The answer cites no passage. Cite the passages that support it, or, if the filings do not answer "
            f'the question, include this exact sentence: "{NO_EVIDENCE_SENTENCE}"'
        )

    passage_figures = [figure for p in passages for figure in parse_figures(p.content, skip_references=False)]
    unsupported: list[str] = []
    for claim in _claims(CITATION_MARKER.sub("", text)):
        if CALCULATION_WORDS.search(claim):
            continue
        for figure in parse_figures(claim, skip_references=True):
            if not _supported(figure, passage_figures) and figure.text not in unsupported:
                unsupported.append(figure.text)
    for figure_text in unsupported:
        violations.append(
            f'"{figure_text}" does not appear in any passage the answer cites. Cite the passage that states it, '
            "say in the same sentence that it is your calculation, or remove it."
        )
    return GroundingReport(violations=violations)
