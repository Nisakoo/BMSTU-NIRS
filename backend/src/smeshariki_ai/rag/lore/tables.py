"""SQLAlchemy Core description of the ``rag_lore_*`` tables.

The tables are owned by the RAG lore subsystem and have no foreign keys to
other modules. The migration ``0015_lore_bm25`` is the source of truth for the
database; a test checks that it matches this description.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY

from smeshariki_ai.rag.models import SLUG_PATTERN

metadata = MetaData()

documents = Table(
    "rag_lore_documents",
    metadata,
    Column("id", Text, primary_key=True),
    Column("title", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("source", Text, nullable=True),
    Column("continuity", Text, nullable=True),
    Column("characters", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("tags", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column(
        "updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint(f"id ~ '{SLUG_PATTERN}'", name="rag_lore_documents_id_format"),
    CheckConstraint("btrim(title) <> ''", name="rag_lore_documents_title_not_blank"),
    CheckConstraint("btrim(text) <> ''", name="rag_lore_documents_text_not_blank"),
)

chunks = Table(
    "rag_lore_chunks",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column(
        "document_id",
        Text,
        ForeignKey("rag_lore_documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("position", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("term_count", Integer, nullable=False),
    UniqueConstraint(
        "document_id", "position", name="rag_lore_chunks_document_position_key"
    ),
    CheckConstraint("position >= 0", name="rag_lore_chunks_position_non_negative"),
    CheckConstraint("term_count >= 0", name="rag_lore_chunks_term_count_non_negative"),
    CheckConstraint("btrim(text) <> ''", name="rag_lore_chunks_text_not_blank"),
)
Index("rag_lore_chunks_document_id_idx", chunks.c.document_id)

terms = Table(
    "rag_lore_terms",
    metadata,
    Column("term", Text, primary_key=True),
    Column("df", Integer, nullable=False),
    CheckConstraint("df >= 1", name="rag_lore_terms_df_positive"),
    CheckConstraint("btrim(term) <> ''", name="rag_lore_terms_term_not_blank"),
)

postings = Table(
    "rag_lore_postings",
    metadata,
    Column(
        "term",
        Text,
        primary_key=True,
    ),
    Column(
        "chunk_id",
        BigInteger,
        ForeignKey("rag_lore_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tf", Integer, nullable=False),
    CheckConstraint("tf >= 1", name="rag_lore_postings_tf_positive"),
)
Index("rag_lore_postings_term_idx", postings.c.term)

stats = Table(
    "rag_lore_stats",
    metadata,
    Column("id", SmallInteger, primary_key=True, server_default=text("1")),
    Column("n_chunks", Integer, nullable=False),
    Column("avgdl", Float, nullable=False),
    Column("version", BigInteger, nullable=False),
    CheckConstraint("id = 1", name="rag_lore_stats_singleton"),
    CheckConstraint("n_chunks >= 0", name="rag_lore_stats_n_chunks_non_negative"),
    CheckConstraint("avgdl >= 0", name="rag_lore_stats_avgdl_non_negative"),
    CheckConstraint("version >= 0", name="rag_lore_stats_version_non_negative"),
)

loads = Table(
    "rag_lore_loads",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("document_count", Integer, nullable=True),
    Column("chunk_count", Integer, nullable=True),
    Column("term_count", Integer, nullable=True),
    CheckConstraint(
        "document_count IS NULL OR document_count >= 0",
        name="rag_lore_loads_document_count_non_negative",
    ),
    CheckConstraint(
        "chunk_count IS NULL OR chunk_count >= 0",
        name="rag_lore_loads_chunk_count_non_negative",
    ),
    CheckConstraint(
        "term_count IS NULL OR term_count >= 0",
        name="rag_lore_loads_term_count_non_negative",
    ),
)
