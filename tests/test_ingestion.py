"""Ingestion: upload CSV/Excel, clean, preview, org isolation."""


def test_upload_requires_auth(client, dirty_csv):
    with open(dirty_csv, "rb") as f:
        r = client.post("/api/datasets/upload",
                        files={"file": ("sales.csv", f, "text/csv")})
    assert r.status_code == 401


def test_upload_csv_cleans(client, auth_headers, dirty_csv):
    with open(dirty_csv, "rb") as f:
        r = client.post("/api/datasets/upload",
                        headers=auth_headers,
                        files={"file": ("sales.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == 5          # 6 rows - 1 exact duplicate
    assert body["cols"] == 4
    assert body["status"] == "ready"
    assert body["name"] == "sales.csv"


def test_upload_rejects_bad_type(client, auth_headers, tmp_path):
    p = tmp_path / "evil.txt"
    p.write_text("hello")
    with open(p, "rb") as f:
        r = client.post("/api/datasets/upload",
                        headers=auth_headers,
                        files={"file": ("evil.txt", f, "text/plain")})
    assert r.status_code == 400
    assert "CSV" in r.json()["detail"] or "Excel" in r.json()["detail"]


def test_datasets_org_scoped(client, auth_headers, dirty_csv):
    with open(dirty_csv, "rb") as f:
        assert client.post("/api/datasets/upload", headers=auth_headers,
                           files={"file": ("sales.csv", f, "text/csv")}).status_code == 200
    # second org
    r2 = client.post("/api/auth/register", json={
        "org_name": "Rival", "name": "Bilal", "email": "b@rival.com", "password": "StrongPass1!"})
    h2 = {"Authorization": f"Bearer {r2.json()['token']}"}
    lst = client.get("/api/datasets", headers=h2)
    assert lst.status_code == 200
    assert lst.json() == []           # no cross-org leakage
    lst1 = client.get("/api/datasets", headers=auth_headers)
    assert len(lst1.json()) == 1


def test_preview(client, auth_headers, dirty_csv):
    with open(dirty_csv, "rb") as f:
        ds = client.post("/api/datasets/upload", headers=auth_headers,
                         files={"file": ("sales.csv", f, "text/csv")}).json()
    r = client.get(f"/api/datasets/{ds['id']}/preview", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["columns"] == ["region", "product", "sales", "date"]
    assert body["dtypes"]["sales"] in ("int64", "float64")
    assert body["nulls"]["sales"] == 0    # empty cell filled/coerced
    assert len(body["rows"]) <= 5
