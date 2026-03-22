"""
Existing test suite — incomplete and partially broken.
Candidate is expected to identify gaps, fix failures, and add security tests.
"""
import pytest
import main
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

VALID_TOKEN = "supersecret-admin-token-1234"


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    """Give every test its own isolated DB so startup event and ordering don't matter."""
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "test_secrets.db"))
    main.init_db()


# ── Passing tests ──────────────────────────────────────────────────────────────

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_secret():
    response = client.post(
        "/secrets",
        json={"name": "db_password", "value": "hunter2", "owner": "alice"},
        headers={"x-token": VALID_TOKEN},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "db_password"


def test_get_secret():
    # Create the secret first so this test is self-contained
    client.post(
        "/secrets",
        json={"name": "db_password", "value": "hunter2", "owner": "alice"},
        headers={"x-token": VALID_TOKEN},
    )
    response = client.get("/secrets/db_password", headers={"x-token": VALID_TOKEN})
    assert response.status_code == 200


# ── Fixed tests ────────────────────────────────────────────────────────────────

def test_create_secret_no_auth():
    response = client.post(
        "/secrets",
        json={"name": "x", "value": "y", "owner": "z"},
    )
    # Fixed: missing token must return 403, not 200
    assert response.status_code == 403


def test_delete_secret():
    client.post(
        "/secrets",
        json={"name": "db_password", "value": "hunter2", "owner": "alice"},
        headers={"x-token": VALID_TOKEN},
    )
    response = client.delete("/secrets/db_password", headers={"x-token": VALID_TOKEN})
    # Fixed: assert deletion response and verify record is gone
    assert response.status_code == 200
    assert response.json() == {"deleted": "db_password"}
    gone = client.get("/secrets/db_password", headers={"x-token": VALID_TOKEN})
    assert gone.status_code == 404


def test_list_secrets_no_auth():
    response = client.get("/secrets")
    # Endpoint is intentionally unauthenticated; assert it returns a list
    assert response.status_code == 200
    assert isinstance(response.json(), list)
