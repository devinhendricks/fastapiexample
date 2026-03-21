"""
Existing test suite — incomplete and partially broken.
Candidate is expected to identify gaps, fix failures, and add security tests.
"""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

VALID_TOKEN = "supersecret-admin-token-1234"


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
    # depends on test_create_secret having run first — fragile ordering
    response = client.get("/secrets/db_password", headers={"x-token": VALID_TOKEN})
    assert response.status_code == 200


# ── Broken / incomplete tests (candidate must fix / complete) ──────────────────

def test_create_secret_no_auth():
    response = client.post(
        "/secrets",
        json={"name": "x", "value": "y", "owner": "z"},
    )
    # BUG: wrong expected status code — should be 403
    assert response.status_code == 200


def test_delete_secret():
    response = client.delete("/secrets/db_password", headers={"x-token": VALID_TOKEN})
    # missing assertion — does not verify deletion actually worked
    pass


def test_list_secrets_no_auth():
    response = client.get("/secrets")
    # Is it okay that this returns 200 with no token?  No assertion captures intent.
    assert response.status_code == 200
