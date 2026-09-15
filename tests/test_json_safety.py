"""JSON safety: nulls in real-world data must never 500 the API.

Regression tests for the NaN -> 500 bug: pandas leaves NaN in frames loaded from
CSV, and NaN/Infinity are not valid JSON, so preview / EDA / ask responses must
sanitise them instead of failing to serialise.
"""
import json


def _upload(client, auth_headers, path):
    with open(path, "rb") as f:
        r = client.post(
            "/api/datasets/upload",
            headers=auth_headers,
            files={"file": ("sales.csv", f, "text/csv")},
        )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_preview_is_json_safe_with_nulls(client, auth_headers, dirty_csv):
    ds = _upload(client, auth_headers, dirty_csv)
    r = client.get(f"/api/datasets/{ds}/preview", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"], "preview must return rows"
    json.dumps(body, allow_nan=False)


def test_eda_is_json_safe_with_nulls(client, auth_headers, dirty_csv):
    ds = _upload(client, auth_headers, dirty_csv)
    r = client.get(f"/api/datasets/{ds}/eda", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "columns" in body and "numeric" in body
    json.dumps(body, allow_nan=False)


def test_ask_fallback_is_json_safe_without_api_key(client, auth_headers, dirty_csv):
    ds = _upload(client, auth_headers, dirty_csv)
    r = client.post(
        f"/api/datasets/{ds}/ask",
        headers=auth_headers,
        json={"question": "which region has the most sales?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "answer" in body or "error" in body
    json.dumps(body, allow_nan=False)
