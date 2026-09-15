from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
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
