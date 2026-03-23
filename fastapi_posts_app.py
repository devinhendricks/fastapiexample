"""
In-memory FastAPI application that implements GET, POST, PUT, PATCH, and DELETE
for a simple "posts" resource.

Used as the server-under-test in test_fastapi_client.py.

Idempotency is enforced at the server level:
  - GET    : Read-only, always returns the same data for the same ID.
  - PUT    : Full replacement — calling with identical data is a no-op effect.
  - DELETE : Returns 204 whether or not the resource existed (state = absent).
  - POST   : Allocates a new auto-incremented ID each call — not idempotent.
  - PATCH  : Updates only supplied fields to absolute values — idempotent here
             because we set fields, not increment them.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Posts API")

# --------------------------------------------------------------------------- #
# In-memory store                                                               #
# --------------------------------------------------------------------------- #

_posts: dict[int, dict] = {}
_next_id: int = 1


def _reset():
    """Clear store between tests."""
    global _next_id
    _posts.clear()
    _next_id = 1


# --------------------------------------------------------------------------- #
# Schemas                                                                       #
# --------------------------------------------------------------------------- #

class PostCreate(BaseModel):
    title: str
    body: str
    user_id: int


class PostReplace(BaseModel):
    title: str
    body: str
    user_id: int


class PostPatch(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    user_id: Optional[int] = None


class Post(BaseModel):
    id: int
    title: str
    body: str
    user_id: int


# --------------------------------------------------------------------------- #
# Endpoints                                                                     #
# --------------------------------------------------------------------------- #

@app.get("/posts/{post_id}", response_model=Post)
def get_post(post_id: int):
    """
    GET — Idempotent and safe.
    Repeated calls with the same post_id return the same resource state.
    """
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")
    return _posts[post_id]


@app.post("/posts", response_model=Post, status_code=201)
def create_post(payload: PostCreate):
    """
    POST — NOT idempotent.
    Each call allocates a new resource with a new auto-incremented ID.
    """
    global _next_id
    post = {"id": _next_id, "title": payload.title, "body": payload.body, "user_id": payload.user_id}
    _posts[_next_id] = post
    _next_id += 1
    return post


@app.put("/posts/{post_id}", response_model=Post)
def replace_post(post_id: int, payload: PostReplace):
    """
    PUT — Idempotent.
    Fully replaces the resource. Sending the same payload twice produces
    the same stored state — no side effects accumulate.
    """
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")
    post = {"id": post_id, "title": payload.title, "body": payload.body, "user_id": payload.user_id}
    _posts[post_id] = post
    return post


@app.patch("/posts/{post_id}", response_model=Post)
def update_post(post_id: int, payload: PostPatch):
    """
    PATCH — Idempotent here because each field is set to an absolute value.
    Only fields included in the payload are changed; omitted fields are preserved.
    """
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")
    post = _posts[post_id]
    if payload.title is not None:
        post["title"] = payload.title
    if payload.body is not None:
        post["body"] = payload.body
    if payload.user_id is not None:
        post["user_id"] = payload.user_id
    return post


@app.delete("/posts/{post_id}", status_code=204)
def delete_post(post_id: int):
    """
    DELETE — Idempotent.
    Whether or not the resource exists, the desired state (absent) is achieved.
    Returns 204 No Content in both cases.
    """
    _posts.pop(post_id, None)   # silently ignore missing — idempotent by design
