"""
Tests for api_client.py

Uses unittest.mock to intercept requests calls — no network required.

Idempotency is verified by:
  - Calling the same function multiple times and asserting the server
    receives identical requests and returns identical results (GET, PUT).
  - Verifying DELETE tolerates a 404 response (already-absent state is valid).
  - Showing POST produces distinct resources on each call.
"""

import unittest
from unittest.mock import patch, MagicMock, call

import api_client


def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    """Build a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()  # no-op unless we configure side_effect
    return mock


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------

class TestGetPost(unittest.TestCase):

    @patch("api_client.requests.get")
    def test_returns_post(self, mock_get):
        expected = {"id": 1, "title": "foo", "body": "bar", "userId": 1}
        mock_get.return_value = _mock_response(200, expected)

        result = api_client.get_post(1)

        mock_get.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/posts/1", timeout=10
        )
        self.assertEqual(result, expected)

    @patch("api_client.requests.get")
    def test_idempotent_repeated_calls_return_same_result(self, mock_get):
        """GET is idempotent: N calls with the same input return the same output."""
        expected = {"id": 1, "title": "foo", "body": "bar", "userId": 1}
        mock_get.return_value = _mock_response(200, expected)

        first  = api_client.get_post(1)
        second = api_client.get_post(1)
        third  = api_client.get_post(1)

        self.assertEqual(first, second)
        self.assertEqual(second, third)
        # Each call hits the server (client-side idempotency — no caching here)
        self.assertEqual(mock_get.call_count, 3)
        # All three calls were identical
        mock_get.assert_called_with(
            "https://jsonplaceholder.typicode.com/posts/1", timeout=10
        )


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------

class TestCreatePost(unittest.TestCase):

    @patch("api_client.requests.post")
    def test_creates_post_and_returns_new_id(self, mock_post):
        expected = {"id": 101, "title": "New Post", "body": "Content", "userId": 1}
        mock_post.return_value = _mock_response(201, expected)

        result = api_client.create_post("New Post", "Content", user_id=1)

        mock_post.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/posts",
            json={"title": "New Post", "body": "Content", "userId": 1},
            timeout=10,
        )
        self.assertEqual(result["id"], 101)
        self.assertEqual(result["title"], "New Post")

    @patch("api_client.requests.post")
    def test_not_idempotent_each_call_gets_different_id(self, mock_post):
        """POST is NOT idempotent: repeated identical requests create distinct resources."""
        mock_post.side_effect = [
            _mock_response(201, {"id": 101, "title": "T", "body": "B", "userId": 1}),
            _mock_response(201, {"id": 102, "title": "T", "body": "B", "userId": 1}),
        ]

        first  = api_client.create_post("T", "B", user_id=1)
        second = api_client.create_post("T", "B", user_id=1)

        # Same input, different IDs — server created two resources
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(mock_post.call_count, 2)


# ---------------------------------------------------------------------------
# PUT
# ---------------------------------------------------------------------------

class TestReplacePost(unittest.TestCase):

    @patch("api_client.requests.put")
    def test_replaces_post(self, mock_put):
        payload = {"id": 1, "title": "Updated", "body": "New body", "userId": 1}
        mock_put.return_value = _mock_response(200, payload)

        result = api_client.replace_post(1, "Updated", "New body", user_id=1)

        mock_put.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/posts/1",
            json={"id": 1, "title": "Updated", "body": "New body", "userId": 1},
            timeout=10,
        )
        self.assertEqual(result["title"], "Updated")
        self.assertEqual(result["body"], "New body")

    @patch("api_client.requests.put")
    def test_idempotent_repeated_calls_produce_same_server_state(self, mock_put):
        """PUT is idempotent: sending the same full payload N times is equivalent to once."""
        expected = {"id": 1, "title": "Updated", "body": "New body", "userId": 1}
        mock_put.return_value = _mock_response(200, expected)

        first  = api_client.replace_post(1, "Updated", "New body", user_id=1)
        second = api_client.replace_post(1, "Updated", "New body", user_id=1)

        self.assertEqual(first, second)
        # Both calls sent the exact same request — compare only the top-level calls
        expected_call = call(
            "https://jsonplaceholder.typicode.com/posts/1",
            json={"id": 1, "title": "Updated", "body": "New body", "userId": 1},
            timeout=10,
        )
        self.assertEqual(mock_put.call_args_list, [expected_call, expected_call])


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------

class TestUpdatePostTitle(unittest.TestCase):

    @patch("api_client.requests.patch")
    def test_partial_update(self, mock_patch):
        expected = {"id": 1, "title": "Patched Title", "body": "original", "userId": 1}
        mock_patch.return_value = _mock_response(200, expected)

        result = api_client.update_post_title(1, "Patched Title")

        mock_patch.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/posts/1",
            json={"title": "Patched Title"},
            timeout=10,
        )
        self.assertEqual(result["title"], "Patched Title")
        # Body was not sent in the request — server preserves it
        self.assertEqual(result["body"], "original")

    @patch("api_client.requests.patch")
    def test_idempotent_when_payload_is_absolute(self, mock_patch):
        """
        PATCH is idempotent here because the payload sets an absolute value.
        If it were {"views": views+1} it would NOT be idempotent.
        """
        expected = {"id": 1, "title": "Stable Title", "body": "b", "userId": 1}
        mock_patch.return_value = _mock_response(200, expected)

        first  = api_client.update_post_title(1, "Stable Title")
        second = api_client.update_post_title(1, "Stable Title")

        self.assertEqual(first["title"], second["title"])


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

class TestDeletePost(unittest.TestCase):

    @patch("api_client.requests.delete")
    def test_successful_delete_returns_200(self, mock_delete):
        mock_delete.return_value = _mock_response(200, {})

        status = api_client.delete_post(1)

        mock_delete.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/posts/1", timeout=10
        )
        self.assertEqual(status, 200)

    @patch("api_client.requests.delete")
    def test_idempotent_second_delete_returns_404_but_state_is_same(self, mock_delete):
        """
        DELETE is idempotent: the desired state (resource absent) holds whether
        the first call returned 200 or the second returned 404.
        Both represent 'resource does not exist'.
        """
        mock_delete.side_effect = [
            _mock_response(200, {}),   # first call: resource existed, now deleted
            _mock_response(404, {}),   # second call: already gone
        ]

        first_status  = api_client.delete_post(1)
        second_status = api_client.delete_post(1)

        # Both are acceptable outcomes — resource is absent in both cases
        self.assertIn(first_status, (200, 204))
        self.assertEqual(second_status, 404)
        self.assertEqual(mock_delete.call_count, 2)

    @patch("api_client.requests.delete")
    def test_delete_204_no_content(self, mock_delete):
        mock_delete.return_value = _mock_response(204, {})

        status = api_client.delete_post(5)

        self.assertEqual(status, 204)


# ---------------------------------------------------------------------------
# Summary table (informational — not a test)
# ---------------------------------------------------------------------------
#
#  Method  | Idempotent | Safe | Creates resource | Notes
#  --------|------------|------|------------------|---------------------------
#  GET     |    YES     | YES  |       NO         | Read-only, no side effects
#  POST    |    NO      | NO   |       YES        | New ID each call
#  PUT     |    YES     | NO   |    YES/replaces  | Full replacement each time
#  PATCH   |  DEPENDS   | NO   |       NO         | Idempotent if absolute vals
#  DELETE  |    YES     | NO   |       NO         | 404 on repeat is still valid
#
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main(verbosity=2)
