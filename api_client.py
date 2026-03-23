"""
HTTP client demonstrating GET, POST, PUT, PATCH, and DELETE.

Idempotency notes:
  - GET    : Idempotent — repeated calls return the same resource state.
  - PUT    : Idempotent — sending the same payload multiple times produces
             the same server state (full replacement each time).
  - DELETE : Idempotent — deleting an already-deleted resource still leaves
             the server in the same state (resource absent). A second call
             typically returns 404, but the *state* is identical.
  - POST   : NOT idempotent — each call creates a new resource.
  - PATCH  : NOT inherently idempotent — e.g. PATCH {"views": views+1}
             produces a different result each call. Can be made idempotent
             if the payload describes absolute state rather than a delta.
"""

import requests
from typing import Any


BASE_URL = "https://jsonplaceholder.typicode.com"


def get_post(post_id: int) -> dict[str, Any]:
    """
    GET /posts/{id}

    Idempotent: calling this any number of times with the same post_id
    always returns the same representation (assuming no mutation between calls).
    """
    response = requests.get(f"{BASE_URL}/posts/{post_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def create_post(title: str, body: str, user_id: int) -> dict[str, Any]:
    """
    POST /posts

    NOT idempotent: each call allocates a new resource with a new ID.
    """
    payload = {"title": title, "body": body, "userId": user_id}
    response = requests.post(f"{BASE_URL}/posts", json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def replace_post(post_id: int, title: str, body: str, user_id: int) -> dict[str, Any]:
    """
    PUT /posts/{id}

    Idempotent: replaces the entire resource. Sending the same payload
    twice leaves the server state identical after the first call.
    """
    payload = {"id": post_id, "title": title, "body": body, "userId": user_id}
    response = requests.put(f"{BASE_URL}/posts/{post_id}", json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def update_post_title(post_id: int, title: str) -> dict[str, Any]:
    """
    PATCH /posts/{id}

    Partially updates a resource. Idempotent here because we set an
    absolute value (not a delta), but this is not guaranteed by the method
    itself — it depends entirely on the payload semantics.
    """
    payload = {"title": title}
    response = requests.patch(f"{BASE_URL}/posts/{post_id}", json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def delete_post(post_id: int) -> int:
    """
    DELETE /posts/{id}

    Idempotent: the desired state (resource absent) is the same whether
    the resource existed before the call or not. Returns the HTTP status code
    so callers can distinguish 200 (deleted) from 404 (already gone).
    """
    response = requests.delete(f"{BASE_URL}/posts/{post_id}", timeout=10)
    # 404 is acceptable — resource already absent is the same end state.
    if response.status_code not in (200, 204, 404):
        response.raise_for_status()
    return response.status_code
