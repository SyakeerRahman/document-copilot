"""Ingest downloaded SEC filings: parse, chunk, embed through OpenRouter, and store in Postgres.

uv run python -m ingest                    # everything in data/downloads/manifest.json
uv run python -m ingest --ticker AAPL      # one company (repeatable)
uv run python -m ingest --dry-run          # parse and chunk only; no API calls, no database
uv run python -m ingest --replace          # re-ingest filings already stored with the current model
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

from app.database.session import create_engine, create_sessionmaker
from ingest.pipeline import IngestError, ManifestEntry, check_embedding_column, ingest_filing, prepare

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "data" / "downloads" / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m ingest", description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ticker", action="append", help="only this ticker (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="parse and chunk only")
    parser.add_argument("--replace", action="store_true", help="re-ingest filings already stored")
    return parser.parse_args()


def load_manifest(path: Path, tickers: list[str] | None) -> list[ManifestEntry]:
    if not path.exists():
        raise IngestError(f"{path} not found. Run `uv run data/download.py` from the repo root first.")
    entries = [ManifestEntry(**filing) for filing in json.loads(path.read_text(encoding="utf-8"))["filings"]]
    if tickers:
        wanted = {ticker.upper() for ticker in tickers}
        entries = [entry for entry in entries if entry.ticker in wanted]
    return entries


async def run(args: argparse.Namespace) -> int:
    entries = load_manifest(args.manifest, args.ticker)
    downloads_dir = args.manifest.parent
    print(f"{len(entries)} filing(s) from {args.manifest}")

    engine = create_engine()
    sessionmaker = create_sessionmaker(engine)
    failures = 0
    started = time.perf_counter()
    try:
        if not args.dry_run:
            await check_embedding_column(sessionmaker)
        async with httpx.AsyncClient() as http:
            for entry in entries:
                label = f"{entry.ticker} FY{entry.report_date[:4]} {entry.accession_number}"
                prepared = prepare(entry, downloads_dir)
                summary = f"{len(prepared.filing.pages)} pages, {len(prepared.document.chunks)} chunks"
                if args.dry_run:
                    print(f"{label}: {summary}")
                    continue
                try:
                    outcome = await ingest_filing(http, sessionmaker, prepared, replace=args.replace)
                except IngestError as exc:
                    failures += 1
                    outcome = f"FAILED: {exc}"
                print(f"{label}: {summary}, {outcome}")
    finally:
        await engine.dispose()

    print(f"done in {time.perf_counter() - started:.0f}s, {failures} failure(s)")
    return 1 if failures else 0


def main() -> None:
    args = parse_args()
    # psycopg async cannot run on Windows' default ProactorEventLoop.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        sys.exit(asyncio.run(run(args), loop_factory=loop_factory))
    except IngestError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
