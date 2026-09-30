"""One-click demo login: only the flagged synthetic demo personas, ordinary customer-scoped tokens."""
import pytest

pytestmark = pytest.mark.needs_db

DEMO = {1: "Lotte", 2: "Julien", 3: "Emma", 4: "Marc", 113: "Jens"}


@pytest.mark.parametrize("cid", sorted(DEMO))
def test_demo_persona_opens_with_one_click(client, cid):
    r = client.post("/api/auth/demo-login", json={"customer_id": cid})
    assert r.status_code == 200 and r.json()["demo"] is True
    me = client.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
    assert me["customer_id"] == cid and me["first_name"] == DEMO[cid]


@pytest.mark.parametrize("cid", [5, 42, 999_999])
def test_non_demo_customers_are_refused(client, cid):
    r = client.post("/api/auth/demo-login", json={"customer_id": cid})
    assert r.status_code == 403 and "token" not in r.json()


@pytest.mark.parametrize("body", [{}, {"customer_id": 0}, {"customer_id": 2**31}, {"customer_id": "1 OR 1=1"}])
def test_bad_bodies_are_422(client, body):
    assert client.post("/api/auth/demo-login", json=body).status_code == 422


def test_demo_token_only_opens_its_own_twin(client):
    tok = client.post("/api/auth/demo-login", json={"customer_id": 1}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/me?customer_id=2", headers=h).json()["customer_id"] == 1
    assert client.get("/api/ops/overview", headers=h).status_code == 401


def test_can_be_switched_off(client, monkeypatch):
    monkeypatch.setenv("TWIN_DEMO_LOGIN", "0")
    assert client.post("/api/auth/demo-login", json={"customer_id": 1}).status_code == 404


def test_rate_limited(client):
    codes = [client.post("/api/auth/demo-login", json={"customer_id": 1}).status_code for _ in range(32)]
    assert codes[:30] == [200] * 30 and codes[-1] == 429
