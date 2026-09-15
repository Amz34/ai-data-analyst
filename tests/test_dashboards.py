"""Dashboards: auto-generated Plotly charts from a dataset, org-scoped."""
import pytest

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


def test_create_dashboard_generates_charts(client, auth_headers, ds):
    r = client.post(
        f"/api/datasets/{ds}/dashboard",
        headers=auth_headers,
        json={"name": "Sales Overview"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Sales Overview"
    assert len(body["charts"]) >= 2  # categorical bar + numeric histogram
    for ch in body["charts"]:
        assert "data" in ch and "layout" in ch


def test_dashboard_org_scoped(client, auth_headers, ds):
    r = client.post(
        f"/api/datasets/{ds}/dashboard",
        headers=auth_headers,
        json={"name": "Secret Dash"},
    )
    assert r.status_code == 201, r.text
    dash_id = r.json()["id"]

    # second org user
    r = client.post(
        "/api/auth/register",
        json={
            "org_name": "RivalCorp",
            "name": "Rival User",
            "email": "rival@test.com",
            "password": "StrongPass1!",
        },
    )
    assert r.status_code == 200  # register contract: 200 (matches conftest/auth suite)
    r = client.post(
        "/api/auth/login",
        json={"email": "rival@test.com", "password": "StrongPass1!"},
    )
    rival_headers = {"Authorization": f"Bearer {r.json()['token']}"}

    assert client.get(f"/api/dashboards/{dash_id}", headers=rival_headers).status_code == 404
    # owner can fetch
    ok = client.get(f"/api/dashboards/{dash_id}", headers=auth_headers)
    assert ok.status_code == 200
    assert len(ok.json()["charts"]) >= 2


def test_list_dashboards_org_scoped(client, auth_headers, ds):
    client.post(f"/api/datasets/{ds}/dashboard", headers=auth_headers, json={"name": "D1"})
    r = client.get("/api/dashboards", headers=auth_headers)
    assert r.status_code == 200
    assert any(d["name"] == "D1" for d in r.json())
