"""Live smoke test against the deployed AI Data Analyst API."""
import io, json, sys
import httpx

BASE = "http://127.0.0.1:8001"
c = httpx.Client(base_url=BASE, timeout=30, follow_redirects=True)
def register_or_login(c, email, password, name, org_name):
    r = c.post("/api/auth/register", json={
        "email": email, "password": password, "name": name, "org_name": org_name,
    })
    if r.status_code == 409:
        r = c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, f"login: {r.status_code} {r.text}"
        return r.json()["token"], False
    assert r.status_code == 200, f"register: {r.status_code} {r.text}"
    return r.json()["token"], True


token, created = register_or_login(c, "demo@smokecorp.com", "StrongPass1!", "Demo User", "SmokeCorp")
print("AUTH:", "registered" if created else "existing")
h = {"Authorization": f"Bearer {token}"}

csv_data = "region,category,sales,units,date\nEast,Electronics,600,12,2026-01-05\nWest,Electronics,400,8,2026-01-12\nEast,Clothing,300,20,2026-02-01\nWest,Clothing,250,15,2026-02-14\nEast,Furniture,900,5,2026-03-02\nWest,Furniture,700,4,2026-03-20\n"
files = {"file": ("sales.csv", io.BytesIO(csv_data.encode()), "text/csv")}
r = c.post("/api/datasets/upload", headers=h, files=files)
assert r.status_code == 200, f"upload: {r.status_code} {r.text}"
ds_id = r.json()["id"]
print(f"1. upload       -> dataset #{ds_id}")

r = c.get(f"/api/datasets/{ds_id}/eda", headers=h)
assert r.status_code == 200, f"eda: {r.status_code} {r.text}"
eda = r.json()
print(f"2. auto-EDA     -> {eda['rows']} rows x {eda['columns']} cols, {len(eda.get('numeric', []))} numeric")

r = c.post(f"/api/datasets/{ds_id}/dashboard", headers=h, json={"name": "Sales Overview"})
assert r.status_code == 201, f"dashboard: {r.status_code} {r.text}"
dash = r.json()
print(f"3. dashboard    -> {dash['name']} with {len(dash['charts'])} charts")

r = c.get("/api/dashboards", headers=h)
assert r.status_code == 200 and len(r.json()) >= 1, f"list: {r.status_code}"
print(f"4. list         -> {len(r.json())} dashboard(s)")

r = c.post(f"/api/datasets/{ds_id}/ask", headers=h, json={"question": "What is total sales by region?"})
assert r.status_code == 200, f"ask: {r.status_code} {r.text}"
body = r.json()
print(f"5. ask          -> result={body.get('result')}")

# org isolation check: second org must NOT see the dashboard
r = c.post("/api/auth/register", json={
    "email": "rival@rivalcorp.com", "password": "StrongPass1!",
    "name": "Rival", "org_name": "RivalCorp",
})
rival_h = {"Authorization": f"Bearer {r.json()['token']}"}
r = c.get(f"/api/dashboards/{dash['id']}", headers=rival_h)
assert r.status_code == 404, f"org isolation: {r.status_code}"
print("6. org isolation -> rival blocked (404) ✓")
print("SMOKE TEST: ALL GREEN")
