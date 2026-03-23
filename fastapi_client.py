"""
HTTP client using httpx — the async-native client recommended for use with FastAPI.

This mirrors api_client.py (which used requests) but uses httpx, which:
  - Supports async/await natively
  - Is the client used internally by FastAPI's TestClient
  - Has an API nearly identical to requests, making migration straightforward

Idempotency contract is identical to api_client.py — see method docstrings.
"""

import httpx
from typing import Any

BASE_URL = "https://jsonplaceholder.typicode.com"


def _get(c: httpx.Client, standalone: bool, *args, **kwargs):
    """Issue GET, adding timeout only for standalone (non-injected) clients."""
    if standalone:
        kwargs.setdefault("timeout", 10)
    return c.get(*args, **kwargs)


def _post(c: httpx.Client, standalone: bool, *args, **kwargs):
    if standalone:
        kwargs.setdefault("timeout", 10)
    return c.post(*args, **kwargs)


def _put(c: httpx.Client, standalone: bool, *args, **kwargs):
    if standalone:
        kwargs.setdefault("timeout", 10)
    return c.put(*args, **kwargs)


def _patch(c: httpx.Client, standalone: bool, *args, **kwargs):
    if standalone:
        kwargs.setdefault("timeout", 10)
    return c.patch(*args, **kwargs)


def _delete(c: httpx.Client, standalone: bool, *args, **kwargs):
    if standalone:
        kwargs.setdefault("timeout", 10)
    return c.delete(*args, **kwargs)


def get_post(post_id: int, *, client: httpx.Client | None = None) -> dict[str, Any]:
    """
    GET /posts/{id}

    Idempotent: repeated calls with the same ID return the same resource state.
    Accepts an optional pre-built client (e.g. FastAPI TestClient) for testing.
    """
    standalone = client is None
    c = client or httpx.Client(base_url=BASE_URL)
    try:
        response = _get(c, standalone, f"/posts/{post_id}")
        response.raise_for_status()
        return response.json()
    finally:
        if standalone:
            c.close()


def create_post(
    title: str,
    body: str,
    user_id: int,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """
    POST /posts

    NOT idempotent: each call creates a distinct resource with a new ID.
    """
    payload = {"title": title, "body": body, "user_id": user_id}
    standalone = client is None
    c = client or httpx.Client(base_url=BASE_URL)
    try:
        response = _post(c, standalone, "/posts", json=payload)
        response.raise_for_status()
        return response.json()
    finally:
        if standalone:
            c.close()


def replace_post(
    post_id: int,
    title: str,
    body: str,
    user_id: int,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """
    PUT /posts/{id}

    Idempotent: fully replaces the resource. Sending the same payload repeatedly
    leaves the server in an identical state after every call.
    """
    payload = {"title": title, "body": body, "user_id": user_id}
    standalone = client is None
    c = client or httpx.Client(base_url=BASE_URL)
    try:
        response = _put(c, standalone, f"/posts/{post_id}", json=payload)
        response.raise_for_status()
        return response.json()
    finally:
        if standalone:
            c.close()


def update_post_title(
    post_id: int,
    title: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """
    PATCH /posts/{id}

    Idempotent here because we set an absolute value. Would NOT be idempotent
    if the payload expressed a delta (e.g. increment a counter).
    """
    payload = {"title": title}
    standalone = client is None
    c = client or httpx.Client(base_url=BASE_URL)
    try:
        response = _patch(c, standalone, f"/posts/{post_id}", json=payload)
        response.raise_for_status()
        return response.json()
    finally:
        if standalone:
            c.close()


def delete_post(
    post_id: int,
    *,
    client: httpx.Client | None = None,
) -> int:
    """
    DELETE /posts/{id}

    Idempotent: resource absent is the desired state whether the first call
    returned 200/204 or a repeat call returns 404.
    """
    standalone = client is None
    c = client or httpx.Client(base_url=BASE_URL)
    try:
        response = _delete(c, standalone, f"/posts/{post_id}")
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()
        return response.status_code
    finally:
        if standalone:
            c.close()
