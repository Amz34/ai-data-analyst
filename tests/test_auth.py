"""Auth: register, login, JWT, org scoping."""


def test_register_success(client):
    r = client.post("/api/auth/register", json={
        "org_name": "ACME", "name": "Ali", "email": "ali@acme.com", "password": "StrongPass1!",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["email"] == "ali@acme.com"
    assert body["user"]["org"]["name"] == "ACME"


def test_register_duplicate_email(client):
    payload = {"org_name": "Acme", "name": "Xavier", "email": "dup@x.com", "password": "StrongPass1!"}
    assert client.post("/api/auth/register", json=payload).status_code == 200
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_register_weak_password(client):
    r = client.post("/api/auth/register", json={
        "org_name": "A", "name": "X", "email": "weak@x.com", "password": "123",
    })
    assert r.status_code == 422  # pydantic validation


def test_login_success(client):
    client.post("/api/auth/register", json={
        "org_name": "ACME", "name": "Ali", "email": "ali@acme.com", "password": "StrongPass1!",
    })
    r = client.post("/api/auth/login", json={"email": "ali@acme.com", "password": "StrongPass1!"})
    assert r.status_code == 200, r.text
    assert r.json()["token"]


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={
        "org_name": "ACME", "name": "Ali", "email": "ali@acme.com", "password": "StrongPass1!",
    })
    assert client.post("/api/auth/login", json={"email": "ali@acme.com", "password": "nope"}).status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_user(client, auth_headers):
    r = client.get("/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "t@test.com"
    assert r.json()["org"]["name"] == "TestCorp"
