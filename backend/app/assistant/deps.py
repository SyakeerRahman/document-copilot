from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

from app.assistant.citations import PassageRegistry
from app.database.documents import CorpusCompany
from app.retrieval.models import SearchFilters, SourcePassage

SearchFn = Callable[[str, SearchFilters], Awaitable[list[SourcePassage]]]
ChunkRangeFn = Callable[[UUID, int, int], Awaitable[list[SourcePassage]]]


@dataclass
class AgentDeps:
    """Everything one chat turn's agent run may touch. Tests pass fakes; production passes database-backed calls."""

    search: SearchFn
    chunks_in_range: ChunkRangeFn
    corpus: list[CorpusCompany]
    passages: PassageRegistry = field(default_factory=PassageRegistry)
