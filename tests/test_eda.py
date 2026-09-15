"""Auto-EDA: deterministic stats computation + AI narrative fallback."""


def _upload(client, auth_headers, tmp_path):
    p = tmp_path / "data.csv"
    p.write_text(
        "region,product,sales,qty,date\n"
        "East,Widget,100,4,2026-01-01\n"
        "East,Gadget,200,8,2026-01-02\n"
        "West,Widget,150,6,2026-01-03\n"
        "West,Gadget,250,10,2026-01-04\n"
        "East,Widget,300,12,2026-01-05\n",
        encoding="utf-8",
    )
    with open(p, "rb") as f:
        ds = client.post("/api/datasets/upload", headers=auth_headers,
                         files={"file": ("data.csv", f, "text/csv")}).json()
    return ds


def test_eda_numeric_stats(client, auth_headers, tmp_path):
    ds = _upload(client, auth_headers, tmp_path)
    r = client.get(f"/api/datasets/{ds['id']}/eda", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    nums = body["numeric"]
    assert nums["sales"]["mean"] == 200.0
    assert nums["sales"]["sum"] == 1000
    assert nums["qty"]["max"] == 12
    assert set(body["columns"]) == {"region", "product", "sales", "qty", "date"}


def test_eda_categorical(client, auth_headers, tmp_path):
    ds = _upload(client, auth_headers, tmp_path)
    body = client.get(f"/api/datasets/{ds['id']}/eda", headers=auth_headers).json()
    cats = {c["column"]: c for c in body["categorical"]}
    assert cats["region"]["top"] == "East"
    assert cats["region"]["counts"]["East"] == 3
    assert cats["product"]["unique"] == 2


def test_eda_has_narrative_even_without_llm(client, auth_headers, tmp_path):
    ds = _upload(client, auth_headers, tmp_path)
    body = client.get(f"/api/datasets/{ds['id']}/eda", headers=auth_headers).json()
    assert "narrative" in body          # may be fallback text; must not 500
    assert isinstance(body["narrative"], str)
