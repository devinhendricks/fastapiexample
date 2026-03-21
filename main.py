"""
Secrets Manager API Service
Internal tool for storing and retrieving application secrets.
"""
import os
import sqlite3
import subprocess
import hashlib
import logging

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

# TODO: move to env var later
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
DB_PATH = "secrets.db"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(title="Secrets Manager API", version="1.0.0")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS secrets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            owner TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


class SecretCreate(BaseModel):
    name: str
    value: str
    owner: str


class SecretResponse(BaseModel):
    id: int
    name: str
    value: str
    owner: str


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/secrets", response_model=SecretResponse)
def create_secret(secret: SecretCreate, x_token: Optional[str] = Header(None)):
    if x_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_db()
    conn.execute(
        "INSERT INTO secrets (name, value, owner) VALUES (?, ?, ?)",
        (secret.name, secret.value, secret.owner),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM secrets WHERE name = ?", (secret.name,)
    ).fetchone()
    conn.close()
    return dict(row)


@app.get("/secrets/{secret_name}", response_model=SecretResponse)
def get_secret(secret_name: str, x_token: Optional[str] = Header(None)):
    if x_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM secrets WHERE name = ?", (secret_name,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Secret not found")

    logger.info(f"Secret retrieved: name={secret_name}, value={row['value']}")
    return dict(row)


@app.delete("/secrets/{secret_name}")
def delete_secret(secret_name: str, x_token: Optional[str] = Header(None)):
    if x_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_db()
    conn.execute("DELETE FROM secrets WHERE name = ?", (secret_name,))
    conn.commit()
    conn.close()
    return {"deleted": secret_name}


@app.post("/admin/run")
def run_command(cmd: str, x_token: Optional[str] = Header(None)):
    """Admin endpoint to run diagnostic commands on the host."""
    if x_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = subprocess.check_output(cmd, shell=True, text=True)
    return {"output": result}


@app.get("/secrets")
def list_secrets():
    """List all secret names (no auth required — names are not sensitive)."""
    conn = get_db()
    rows = conn.execute("SELECT id, name, owner FROM secrets").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()
