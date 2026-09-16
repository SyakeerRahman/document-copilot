import re
from dataclasses import dataclass
from uuid import UUID

from app.retrieval.models import SourcePassage

# The model cites a passage by the handle its tool result showed, for example [P3].
CITATION_MARKER = re.compile(r"\[(P\d+)\]")


class PassageRegistry:
    """Handles for every passage shown to the model during one chat turn.

    A handle is the only thing the model can cite, and code resolves it back to the exact chunk. A chunk
    returned by two searches keeps its first handle, so one passage never has two names.
    """

    def __init__(self) -> None:
        self._by_handle: dict[str, SourcePassage] = {}
        self._handle_by_chunk: dict[UUID, str] = {}

    def register(self, passage: SourcePassage) -> str:
        handle = self._handle_by_chunk.get(passage.chunk_id)
        if handle is None:
            handle = f"P{len(self._by_handle) + 1}"
            self._by_handle[handle] = passage
            self._handle_by_chunk[passage.chunk_id] = handle
        return handle

    def get(self, handle: str) -> SourcePassage | None:
        return self._by_handle.get(handle)

    def __len__(self) -> int:
        return len(self._by_handle)


@dataclass(frozen=True)
class Citation:
    handle: str
    passage: SourcePassage


@dataclass(frozen=True)
class CitedAnswer:
    text: str
    citations: list[Citation]
    # Handles in the text that no tool result ever showed. Grounding (step 12) treats any as a failure.
    unknown_handles: list[str]


def extract_citations(text: str, registry: PassageRegistry) -> CitedAnswer:
    citations: list[Citation] = []
    unknown: list[str] = []
    for handle in dict.fromkeys(CITATION_MARKER.findall(text)):  # first-appearance order, no repeats
        passage = registry.get(handle)
        if passage is None:
            unknown.append(handle)
        else:
            citations.append(Citation(handle, passage))
    return CitedAnswer(text=text, citations=citations, unknown_handles=unknown)


def strip_citation_markers(text: str) -> str:
    # Earlier answers go back to the model as history. Their handles belonged to an earlier turn's registry
    # and would resolve to different passages now, so they are removed before the model sees them.
    return re.sub(r" ?\[P\d+\]", "", text)
