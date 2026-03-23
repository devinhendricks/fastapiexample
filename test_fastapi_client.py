"""
Tests for fastapi_posts_app.py and fastapi_client.py

Uses FastAPI's TestClient (backed by httpx) — no mock patching needed because
the entire server runs in-process. This lets us verify idempotency at the
*server state* level, not just at the HTTP call level.

Two test suites:

  TestFastapiApp        — tests the FastAPI endpoints directly via TestClient
  TestFastapiClientFns  — tests fastapi_client.py helper functions by injecting
                          a TestClient as the httpx.Client dependency

Each suite resets the in-memory store in setUp so tests are fully isolated.
"""

import unittest
from fastapi.testclient import TestClient

import fastapi_posts_app as app_module
from fastapi_posts_app import app
import fastapi_client as client_module


# Shared TestClient instance (safe — TestClient is synchronous and thread-local)
tc = TestClient(app, raise_server_exceptions=True)


def _seed_post(title="Original", body="Body", user_id=1) -> int:
    """Helper: create a post and return its ID."""
    r = tc.post("/posts", json={"title": title, "body": body, "user_id": user_id})
    assert r.status_code == 201
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Direct endpoint tests
# ---------------------------------------------------------------------------

class TestFastapiApp(unittest.TestCase):

    def setUp(self):
        app_module._reset()

    # --- GET ---

    def test_get_returns_post(self):
        post_id = _seed_post(title="Hello")
        r = tc.get(f"/posts/{post_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["title"], "Hello")

    def test_get_idempotent_repeated_calls_return_same_body(self):
        """GET is idempotent: the resource is unchanged across N reads."""
        post_id = _seed_post(title="Stable")
        results = [tc.get(f"/posts/{post_id}").json() for _ in range(3)]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])

    def test_get_404_for_missing_post(self):
        r = tc.get("/posts/999")
        self.assertEqual(r.status_code, 404)

    # --- POST ---

    def test_post_creates_resource_with_new_id(self):
        r = tc.post("/posts", json={"title": "T", "body": "B", "user_id": 1})
        self.assertEqual(r.status_code, 201)
        self.assertIn("id", r.json())

    def test_post_not_idempotent_each_call_gets_unique_id(self):
        """POST is NOT idempotent: identical payloads produce distinct resources."""
        payload = {"title": "Same", "body": "Same", "user_id": 1}
        first  = tc.post("/posts", json=payload).json()
        second = tc.post("/posts", json=payload).json()
        self.assertNotEqual(first["id"], second["id"])

    # --- PUT ---

    def test_put_replaces_all_fields(self):
        post_id = _seed_post(title="Old Title", body="Old Body")
        r = tc.put(f"/posts/{post_id}", json={"title": "New Title", "body": "New Body", "user_id": 2})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["title"], "New Title")
        self.assertEqual(data["body"], "New Body")
        self.assertEqual(data["user_id"], 2)

    def test_put_idempotent_second_call_produces_identical_state(self):
        """PUT is idempotent: sending the same full payload twice leaves identical state."""
        post_id = _seed_post()
        payload = {"title": "Replaced", "body": "Replaced Body", "user_id": 5}

        first  = tc.put(f"/posts/{post_id}", json=payload).json()
        second = tc.put(f"/posts/{post_id}", json=payload).json()

        self.assertEqual(first, second)
        # Verify actual stored state — not just response equality
        stored = tc.get(f"/posts/{post_id}").json()
        self.assertEqual(stored["title"], "Replaced")

    def test_put_404_for_missing_post(self):
        r = tc.put("/posts/999", json={"title": "X", "body": "Y", "user_id": 1})
        self.assertEqual(r.status_code, 404)

    # --- PATCH ---

    def test_patch_updates_only_supplied_fields(self):
        post_id = _seed_post(title="Original Title", body="Original Body")
        r = tc.patch(f"/posts/{post_id}", json={"title": "Patched Title"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["title"], "Patched Title")
        self.assertEqual(data["body"], "Original Body")   # untouched

    def test_patch_idempotent_when_payload_is_absolute(self):
        """
        PATCH with an absolute value is idempotent: applying it twice
        leaves the same server state as applying it once.
        """
        post_id = _seed_post(title="Before")

        first  = tc.patch(f"/posts/{post_id}", json={"title": "After"}).json()
        second = tc.patch(f"/posts/{post_id}", json={"title": "After"}).json()

        self.assertEqual(first["title"], second["title"])
        self.assertEqual(tc.get(f"/posts/{post_id}").json()["title"], "After")

    def test_patch_404_for_missing_post(self):
        r = tc.patch("/posts/999", json={"title": "X"})
        self.assertEqual(r.status_code, 404)

    # --- DELETE ---

    def test_delete_removes_resource(self):
        post_id = _seed_post()
        r = tc.delete(f"/posts/{post_id}")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(tc.get(f"/posts/{post_id}").status_code, 404)

    def test_delete_idempotent_second_call_also_returns_204(self):
        """
        DELETE is idempotent: the server always returns 204 because the
        endpoint silently ignores missing resources (pop with default).
        The desired state — resource absent — holds after both calls.
        """
        post_id = _seed_post()

        first_status  = tc.delete(f"/posts/{post_id}").status_code
        second_status = tc.delete(f"/posts/{post_id}").status_code

        self.assertEqual(first_status, 204)
        self.assertEqual(second_status, 204)   # 204, not 404 — idempotent by design

    def test_delete_nonexistent_post_still_returns_204(self):
        r = tc.delete("/posts/9999")
        self.assertEqual(r.status_code, 204)


# ---------------------------------------------------------------------------
# fastapi_client.py helper function tests
# (injects TestClient so no real network calls are made)
# ---------------------------------------------------------------------------

class TestFastapiClientFns(unittest.TestCase):
    """
    Injects the FastAPI TestClient as the httpx.Client dependency.
    TestClient implements the same interface as httpx.Client, so the
    client functions accept it transparently via the `client=` kwarg.
    """

    def setUp(self):
        app_module._reset()
        # Seed a post that tests can reference
        r = tc.post("/posts", json={"title": "Seed", "body": "Seed body", "user_id": 1})
        self.post_id = r.json()["id"]

    def test_get_post(self):
        result = client_module.get_post(self.post_id, client=tc)
        self.assertEqual(result["id"], self.post_id)
        self.assertEqual(result["title"], "Seed")

    def test_create_post(self):
        result = client_module.create_post("New", "Body", user_id=1, client=tc)
        self.assertIn("id", result)
        self.assertEqual(result["title"], "New")

    def test_replace_post(self):
        result = client_module.replace_post(
            self.post_id, "Replaced", "Replaced body", user_id=2, client=tc
        )
        self.assertEqual(result["title"], "Replaced")
        self.assertEqual(result["user_id"], 2)

    def test_update_post_title(self):
        result = client_module.update_post_title(self.post_id, "Patched", client=tc)
        self.assertEqual(result["title"], "Patched")
        self.assertEqual(result["body"], "Seed body")   # body unchanged

    def test_delete_post(self):
        status = client_module.delete_post(self.post_id, client=tc)
        self.assertEqual(status, 204)

    def test_delete_post_idempotent(self):
        client_module.delete_post(self.post_id, client=tc)
        status = client_module.delete_post(self.post_id, client=tc)
        self.assertEqual(status, 204)


# ---------------------------------------------------------------------------
# Summary table (informational)
# ---------------------------------------------------------------------------
#
#  Method  | Idempotent | Safe | Server behaviour in this app
#  --------|------------|------|---------------------------------------------
#  GET     |    YES     | YES  | Returns post or 404; no mutation
#  POST    |    NO      | NO   | Allocates new ID each call
#  PUT     |    YES     | NO   | Full replacement; same payload = same state
#  PATCH   |  YES here  | NO   | Sets absolute field values; no deltas
#  DELETE  |    YES     | NO   | pop() with default; always 204
#
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main(verbosity=2)
