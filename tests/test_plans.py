"""Commercial layer tests: plan defaults, quotas, metering, admin activation."""
import pytest

from app import config


def _upload(client, headers, path, name="sales.csv"):
    with open(path, "rb") as fh:
        return client.post(
            "/api/datasets/upload",
            files={"file": (name, fh, "text/csv")},
            headers=headers,
        )


def test_registration_starts_on_trial(client, auth_headers):
    r = client.get("/api/billing/me", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan"] == "trial"
    assert body["status"] == "active"
    assert body["limits"]["dataset"] == config.PLAN_LIMITS["trial"]["dataset"]
    assert body["usage"]["dataset"]["used"] == 0


def test_dataset_quota_enforced(client, auth_headers, dirty_csv):
    cap = config.PLAN_LIMITS["trial"]["dataset"]
    for i in range(cap):
        assert _upload(client, auth_headers, dirty_csv).status_code == 200
    r = _upload(client, auth_headers, dirty_csv)
    assert r.status_code == 402, r.text
    assert "Upgrade" in r.json()["detail"]
    me = client.get("/api/billing/me", headers=auth_headers).json()
    assert me["usage"]["dataset"]["used"] == cap


def test_upload_size_limit_follows_plan(client, auth_headers, dirty_csv, monkeypatch):
    monkeypatch.setitem(config.PLAN_LIMITS["trial"], "max_upload_mb", 0)
    r = _upload(client, auth_headers, dirty_csv)
    assert r.status_code == 413, r.text
    assert "plan" in r.json()["detail"]


def test_ask_is_metered_and_capped(client, auth_headers, dirty_csv, monkeypatch):
    ds = _upload(client, auth_headers, dirty_csv).json()
    monkeypatch.setitem(config.PLAN_LIMITS["trial"], "ask", 2)
    for _ in range(2):
        r = client.post(f"/api/datasets/{ds['id']}/ask", json={"question": "how many rows?"}, headers=auth_headers)
        assert r.status_code == 200, r.text
    r = client.post(f"/api/datasets/{ds['id']}/ask", json={"question": "and now?"}, headers=auth_headers)
    assert r.status_code == 402, r.text
    me = client.get("/api/billing/me", headers=auth_headers).json()
    assert me["usage"]["ask"]["used"] == 2


def test_admin_requires_token_and_can_upgrade(client, auth_headers, dirty_csv, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    assert client.get("/api/admin/orgs").status_code == 401
    admin = {"X-Admin-Token": "s3cret"}
    orgs = client.get("/api/admin/orgs", headers=admin)
    assert orgs.status_code == 200, orgs.text
    org_id = orgs.json()[0]["org_id"]

    cap = config.PLAN_LIMITS["trial"]["dataset"]
    for _ in range(cap):
        assert _upload(client, auth_headers, dirty_csv).status_code == 200
    assert _upload(client, auth_headers, dirty_csv).status_code == 402

    r = client.post(f"/api/admin/orgs/{org_id}/plan", json={"plan": "starter", "paid_until": "2026-10-14", "billing_note": "SAR 1500 bank transfer"}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == "starter"
    assert r.json()["paid_until"].startswith("2026-10-14")

    # the upgrade unblocks the action that was quota-blocked a moment ago
    assert _upload(client, auth_headers, dirty_csv).status_code == 200


def test_admin_rejects_unknown_plan(client, auth_headers, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    admin = {"X-Admin-Token": "s3cret"}
    org_id = client.get("/api/admin/orgs", headers=admin).json()[0]["org_id"]
    r = client.post(f"/api/admin/orgs/{org_id}/plan", json={"plan": "enterprise"}, headers=admin)
    assert r.status_code == 400


def test_suspended_org_is_blocked(client, auth_headers, dirty_csv, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    r = client.get("/api/billing/me", headers=auth_headers)
    org_id = r.json()["org_id"]
    client.post(f"/api/admin/orgs/{org_id}/plan", json={"status": "suspended"}, headers={"X-Admin-Token": "s3cret"})
    blocked = _upload(client, auth_headers, dirty_csv)
    assert blocked.status_code == 403, blocked.text
    assert "suspended" in blocked.json()["detail"].lower()


def test_public_plan_catalogue(client):
    r = client.get("/api/billing/plans")
    assert r.status_code == 200
    plans = r.json()["plans"]
    assert {"trial", "starter", "growth", "pro"} <= set(plans)
    assert plans["growth"]["ask"] > plans["starter"]["ask"]
