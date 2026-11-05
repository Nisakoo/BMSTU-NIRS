"""SQLAlchemy Core description of the tables owned by this backend.

The schema is documented in docs/database.md; migrations are the source of
truth for the database itself.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("login", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("role", Text, nullable=False, server_default=text("'user'")),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column(
        "updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint("login ~ '^[A-Za-z0-9_.-]{3,32}$'", name="users_login_format"),
    CheckConstraint("role IN ('user', 'admin')", name="users_role_valid"),
)
Index("users_login_lower_key", func.lower(users.c.login), unique=True)

refresh_sessions = Table(
    "refresh_sessions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column(
        "user_id",
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("family_id", Uuid, nullable=False, index=True),
    Column("token_hash", LargeBinary, nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column(
        "replaced_by",
        Uuid,
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"),
        nullable=True,
    ),
)

dialogs = Table(
    "dialogs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("title", Text, nullable=True),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column(
        "updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
)
Index("ix_dialogs_user_id_updated_at", dialogs.c.user_id, dialogs.c.updated_at.desc())

messages = Table(
    "messages",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column(
        "dialog_id",
        Uuid,
        ForeignKey("dialogs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("position", Integer, nullable=False),
    Column("role", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    UniqueConstraint("dialog_id", "position", name="messages_dialog_id_position_key"),
    CheckConstraint("role IN ('user', 'assistant')", name="messages_role_valid"),
)

message_feedback = Table(
    "message_feedback",
    metadata,
    Column(
        "message_id",
        BigInteger,
        ForeignKey("messages.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("score", SmallInteger, nullable=False),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column(
        "updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint("score BETWEEN 1 AND 5", name="message_feedback_score_valid"),
)

# A report keeps copies of the texts: the user may delete the dialog later.
message_reports = Table(
    "message_reports",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column(
        "message_id",
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    ),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("reason", Text, nullable=False),
    Column("comment", Text, nullable=True),
    Column("request_text", Text, nullable=True),
    Column("answer_text", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'new'")),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column("resolved_at", DateTime(timezone=True), nullable=True),
    Column(
        "resolved_by", Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    ),
    # When the user dismissed the news that the report was reviewed.
    Column("seen_at", DateTime(timezone=True), nullable=True),
    CheckConstraint(
        "reason IN ('scary', 'rude', 'wrong', 'other')",
        name="message_reports_reason_valid",
    ),
    CheckConstraint(
        "status IN ('new', 'resolved', 'dismissed')",
        name="message_reports_status_valid",
    ),
    CheckConstraint(
        "char_length(comment) <= 500", name="message_reports_comment_length"
    ),
)
Index(
    "ix_message_reports_status_created_at",
    message_reports.c.status,
    message_reports.c.created_at.desc(),
)
