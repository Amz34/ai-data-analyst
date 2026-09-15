import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app import config as cfg


@pytest.fixture()
def client():
    # Hermetic in-memory DB for tests
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import app/models FIRST so ORM metadata is populated before create_all
    from app.main import app
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from app.main import app

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    r = client.post("/api/auth/register", json={
        "org_name": "TestCorp",
        "name": "Tester",
        "email": "t@test.com",
        "password": "Secret123!",
    })
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def dirty_csv(tmp_path):
    p = tmp_path / "sales.csv"
    p.write_text(
        "region,product,sales,date\n"
        "East,Widget,100,2026-01-01\n"
        "East,Gadget,,2026-01-02\n"
        "West,Widget,150,2026-01-03\n"
        "East,Widget,100,2026-01-01\n"      # duplicate row
        "West,Gadget,200,not-a-date\n"
        "\n"
        "East,Widget,130,2026-01-04\n",
        encoding="utf-8",
    )
    return p
