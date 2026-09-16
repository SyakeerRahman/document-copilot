"""embedding dimensions 1024 for ollama

Revision ID: c3b7c46fbef0
Revises: f8c72bfbcdba
Create Date: 2026-09-16 18:37:40.945683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = 'c3b7c46fbef0'
down_revision: Union[str, Sequence[str], None] = 'f8c72bfbcdba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX = "document_chunks_embedding_hnsw_idx"


def _set_dimensions(dimensions: int) -> None:
    # Vectors of different sizes cannot be cast, so this only works on an empty table. That is
    # deliberate: vectors from another model are not comparable and must be re-ingested, not kept.
    op.execute(
        "do $$ begin if exists (select 1 from document_chunks) then "
        "raise exception 'document_chunks is not empty: delete the chunks and re-run ingestion'; "
        "end if; end $$"
    )
    op.drop_index(INDEX, table_name="document_chunks")
    op.execute(f"alter table document_chunks alter column embedding type vector({dimensions})")
    op.create_index(
        INDEX,
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def upgrade() -> None:
    """Upgrade schema."""
    # OpenAI text-embedding-3-small (1536) -> Ollama qwen3-embedding:0.6b / bge-m3 (1024).
    _set_dimensions(1024)


def downgrade() -> None:
    """Downgrade schema."""
    _set_dimensions(1536)
