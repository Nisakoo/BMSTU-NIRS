"""SQLAlchemy Core description of the tables owned by this backend.

The schema is documented in docs/database.md; migrations are the source of
truth for the database itself.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    MetaData,
    Table,
    Text,
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
