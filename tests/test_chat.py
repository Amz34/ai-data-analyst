"""Chat-to-data: LLM-written pandas code runs in a sandbox. Tests use monkeypatched LLM."""
import pytest

from app.services import sandbox

CSV = (
    "region,product,sales,qty,date\n"
    "East,Widget,100,4,2026-01-01\n"
    "East,Gadget,200,8,2026-01-02\n"
    "West,Widget,150,6,2026-01-03\n"
    "West,Gadget,250,10,2026-01-04\n"
    "East,Widget,300,12,2026-01-05\n"
)


@pytest.fixture()
def ds(client, auth_headers):
    r = client.post(
        "/api/datasets/upload",
        headers=auth_headers,
        files={"file": ("sales.csv", CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_ask_returns_llm_answer(client, auth_headers, ds, monkeypatch):
    def fake_chat(system, user, max_tokens=400, temperature=0.3):
        return "result = df.groupby('region')['sales'].sum()"

    monkeypatch.setattr("app.routers.datasets_routes.chat", fake_chat)
    r = client.post(
        f"/api/datasets/{ds}/ask",
        headers=auth_headers,
        json={"question": "total sales by region"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "code" in body
    assert body["result"] == {"East": 600.0, "West": 400.0}


def test_ask_fallback_without_llm(client, auth_headers, ds, monkeypatch):
    monkeypatch.setattr("app.routers.datasets_routes.chat", lambda *a, **k: "")
    r = client.post(
        f"/api/datasets/{ds}/ask",
        headers=auth_headers,
        json={"question": "average sales"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["sales"] == pytest.approx(200.0)


def test_ask_bad_code_reports_error(client, auth_headers, ds, monkeypatch):
    def fake_chat(system, user, max_tokens=400, temperature=0.3):
        return "result = 1/0"

    monkeypatch.setattr("app.routers.datasets_routes.chat", fake_chat)
    r = client.post(
        f"/api/datasets/{ds}/ask",
        headers=auth_headers,
        json={"question": "anything"},
    )
    assert r.status_code == 200, r.text
    assert "error" in r.json() and r.json()["error"]


def test_sandbox_blocks_os_import():
    out = sandbox.run_code("import os\nresult = os.listdir('/')", df=None)
    assert out["error"] and "blocked" in out["error"].lower()


def test_sandbox_blocks_network():
    out = sandbox.run_code("import socket\nresult = socket.gethostname()", df=None)
    assert out["error"]


def test_sandbox_blocks_file_write():
    out = sandbox.run_code("df.to_csv('/tmp/leak.csv')\nresult = 1", df=None)
    assert out["error"]


def test_sandbox_timeout():
    out = sandbox.run_code("while True:\n    pass", df=None, timeout=1)
    assert out["error"] and "timeout" in out["error"].lower()


def test_sandbox_runs_pandas():
    import pandas as pd

    df = pd.DataFrame({"region": ["East", "East", "West"], "sales": [1.0, 2.0, 3.0]})
    out = sandbox.run_code("result = df.groupby('region')['sales'].sum()", df=df)
    assert out["ok"] and out["result"] == {"East": 3.0, "West": 3.0}
