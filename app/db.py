from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from . import config


class Base(DeclarativeBase):
    pass


# The default deployment target is Postgres. For a zero-setup local run the DSN can
# be a SQLite file; SQLite then needs a connection that survives FastAPI's threadpool.
_is_sqlite = config.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    config.DATABASE_URL,
    pool_pre_ping=True,
    **(
        {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        if _is_sqlite
        else {}
    ),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> list[str]:
    """Additive, idempotent column migration for already-deployed databases.

    create_all() adds new tables but never new columns, so the commercial
    columns on `orgs` are added here (Postgres only; tests create a fresh DB).
    """
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return []
    statements = [
        "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS plan VARCHAR(20) DEFAULT 'trial'",
        "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'",
        "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS billing_note VARCHAR(255)",
        "ALTER TABLE orgs ADD COLUMN IF NOT EXISTS paid_until TIMESTAMPTZ",
        "UPDATE orgs SET plan = 'trial' WHERE plan IS NULL",
        "UPDATE orgs SET status = 'active' WHERE status IS NULL",
    ]
    applied: list[str] = []
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
            applied.append(stmt)
    return applied
