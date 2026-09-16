"""Answer eval: does the agent answer from the filings and cite the passage that holds the answer?

    uv run python -m evals.answers                  # all questions, CHAT_MODEL from settings
    uv run python -m evals.answers --show-answers   # also print every answer for reading
    uv run python -m evals.answers --model openai/gpt-5-mini-2025-08-07   # compare another OpenRouter model

Answerable questions reuse the retrieval answer key (evals/retrieval_questions.json). Each question is
asked with its company and fiscal year, as an analyst would ask it. For each answer the eval checks:

- cited: the answer has at least one citation.
- valid: every citation handle was shown to the model in this turn (none invented).
- expected: at least one cited passage is an answer-key passage for that question.

Decline questions have no right passage. They are printed for a person to read, because "declined
correctly" is a judgement: a good answer to "should I buy" can still cite filings.
"""

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, replace

import httpx

from app.assistant.agent import build_agent
from app.assistant.answer import AnswerDone, stream_answer
from app.assistant.model import build_chat_model
from app.assistant.runtime import database_deps
from app.config import settings
from app.database.session import create_engine, create_sessionmaker
from evals.retrieval import Question, load_questions

CONCURRENCY = 4
DECLINE_QUESTIONS = (
    "Should I buy NVIDIA stock based on its fiscal 2025 results?",
    "What was Tesla's total revenue in fiscal 2024?",
    "Do Microsoft's 10-K filings prove that generative AI improved its operating margins?",
)


@dataclass(frozen=True)
class Outcome:
    label: str
    prompt: str
    done: AnswerDone | None
    seconds: float
    error: str | None = None
    question: Question | None = None

    @property
    def cited(self) -> bool:
        return bool(self.done and self.done.answer.citations)

    @property
    def valid(self) -> bool:
        return bool(self.done) and not self.done.answer.unknown_handles

    @property
    def expected(self) -> bool:
        return bool(self.done and self.question) and any(
            self.question.is_answer(citation.passage) for citation in self.done.answer.citations
        )


async def ask(agent, deps_factory, label: str, prompt: str, semaphore: asyncio.Semaphore) -> Outcome:
    async with semaphore:
        started = time.perf_counter()
        try:
            deps = await deps_factory()
            done = None
            async for item in stream_answer(agent, prompt, [], deps):
                if isinstance(item, AnswerDone):
                    done = item
            return Outcome(label, prompt, done, time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001 - one failed question must not hide the other results
            return Outcome(label, prompt, None, time.perf_counter() - started, error=f"{type(exc).__name__}: {exc}")


async def run(model_name: str, show_answers: bool) -> int:
    questions = load_questions()
    engine = create_engine()
    sessionmaker = create_sessionmaker(engine)
    agent = build_agent(build_chat_model(settings.model_copy(update={"chat_model": model_name})))
    semaphore = asyncio.Semaphore(CONCURRENCY)

    try:
        async with httpx.AsyncClient() as http:

            async def deps_factory():
                return await database_deps(sessionmaker, http)

            corpus = {company.ticker: company.company_name for company in (await deps_factory()).corpus}
            answerable = [
                ask(
                    agent,
                    deps_factory,
                    q.id,
                    f"{q.question} ({corpus[q.ticker]}, fiscal year {q.fiscal_year})",
                    semaphore,
                )
                for q in questions
            ]
            declines = [
                ask(agent, deps_factory, f"decline-{i}", text, semaphore) for i, text in enumerate(DECLINE_QUESTIONS, 1)
            ]
            results = await asyncio.gather(*answerable, *declines)
    finally:
        await engine.dispose()

    answered = [replace(outcome, question=q) for outcome, q in zip(results[: len(questions)], questions, strict=True)]
    declined = results[len(questions) :]

    print(f"model {model_name}, {len(answered)} answerable questions, {len(declined)} decline questions\n")
    print(f"{'question':38} {'cited':>5} {'valid':>5} {'expected':>8} {'cites':>5} {'secs':>5} {'tokens in/out':>14}")
    for o in answered:
        usage = o.done.usage if o.done else {}
        tokens = f"{usage.get('input_tokens', 0)}/{usage.get('output_tokens', 0)}"
        flags = "ERROR " + (o.error or "")[:60] if o.error else ""
        print(
            f"{o.label:38} {yes(o.cited):>5} {yes(o.valid):>5} {yes(o.expected):>8} "
            f"{len(o.done.answer.citations) if o.done else 0:>5} {o.seconds:5.1f} {tokens:>14} {flags}"
        )

    n = len(answered)
    rate = lambda attr: sum(getattr(o, attr) for o in answered) / n
    seconds = sorted(o.seconds for o in answered)
    total_in = sum((o.done.usage.get("input_tokens") or 0) for o in results if o.done)
    total_out = sum((o.done.usage.get("output_tokens") or 0) for o in results if o.done)
    print(
        f"\ncited {rate('cited'):.2f}   valid {rate('valid'):.2f}   expected {rate('expected'):.2f}   "
        f"median {seconds[n // 2]:.1f}s   max {seconds[-1]:.1f}s   tokens {total_in} in / {total_out} out   "
        f"errors {sum(1 for o in results if o.error)}"
    )

    print("\nDecline questions (read these):")
    for o in declined:
        print(f"\n--- {o.prompt}")
        if o.error:
            print(f"ERROR {o.error}")
            continue
        citations = o.done.answer.citations
        print(f"[{len(citations)} citations, unknown handles {o.done.answer.unknown_handles}]")
        print(o.done.answer.text.strip())

    if show_answers:
        for o in answered:
            print(f"\n=== {o.label}: {o.prompt}")
            print(o.done.answer.text.strip() if o.done else f"ERROR {o.error}")
            for citation in o.done.answer.citations if o.done else []:
                p = citation.passage
                marker = "*" if o.question.is_answer(p) else " "
                print(f"  {marker} {citation.handle}: {p.ticker} FY{p.fiscal_year} p.{p.page_label} {p.section[:45]}")
    return 0


def yes(value: bool) -> str:
    return "yes" if value else "NO"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evals.answers")
    parser.add_argument("--model", default=settings.chat_model, help="OpenRouter model id (default: CHAT_MODEL)")
    parser.add_argument("--show-answers", action="store_true", help="print every answer and its citations")
    args = parser.parse_args()
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    sys.exit(asyncio.run(run(args.model, args.show_answers), loop_factory=loop_factory))


if __name__ == "__main__":
    main()
