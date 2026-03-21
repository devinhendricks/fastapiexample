# Principal DevSecOps Engineer — Technical Interview Scenario

**Role:** Principal DevSecOps Engineer
**Language:** Python 3.10
**Estimated time:** 50 minutes (technical block)

---

## Context (read to candidate — 2 min)

> "We're a fintech company. A junior engineer shipped this internal **Secrets Manager API** last
> sprint. It stores and retrieves application credentials used by CI/CD pipelines. The service
> recently passed an internal code review but has not yet gone to production. Your job today is to
> act as the Principal engineer on-call: review the code, identify problems, fix what you can live,
> and explain your reasoning as you go."

Files provided:
- `main.py` — the FastAPI application
- `test_main.py` — the existing (incomplete) test suite
- `requirements.txt`

---

## Section 1 — Security Code Review (15 min)

### Prompt
> "Walk us through `main.py`. Identify every security vulnerability you can find, explain the risk
> of each, and rank them by severity."

### What we're listening for

| Finding | Severity | Concept tested |
|---|---|---|
| SQL injection in every query (`f"...{secret_name}..."`) | Critical | OWASP A03 Injection |
| Hardcoded admin token (`ADMIN_TOKEN = "supersecret..."`) | Critical | Secrets management, 12-factor app |
| `GET /secrets` unauthenticated — leaks all secret *names* | High | Broken access control (OWASP A01) |
| `POST /admin/run` — arbitrary OS command execution via `shell=True` | Critical | Command injection (OWASP A03) |
| Secret *values* logged at INFO level | High | Sensitive data exposure (OWASP A02) |
| Passwords hashed with MD5 | High | Cryptographic failure (OWASP A02) |
| Token compared with `==` (timing attack surface) | Medium | Side-channel, use `secrets.compare_digest` |
| No rate limiting / brute-force protection on token | Medium | Auth design |
| SQLite in-process DB — not suitable for multi-replica deployment | Low/Design | Stateless service design |

**Strong answer:** Candidate organises findings by OWASP category, explains *why* each is a risk
in a secrets-management context specifically (higher blast radius than a normal app), and
prioritises the Critical trio before anything else.

**Probe questions:**
- "How would an attacker exploit the SQL injection in `GET /secrets/{secret_name}`? Show us the
  payload."
- "The `admin/run` endpoint has auth — why is it still a Critical finding?"
- "What's the risk of logging the secret value even at DEBUG level in production?"

---

## Section 2 — Live Fix: SQL Injection & Hardcoded Secret (15 min)

### Prompt
> "Fix the SQL injection vulnerabilities and the hardcoded token. Show us working code."

### Expected solution — SQL injection

Replace f-string queries with parameterised queries:

```python
# BEFORE (vulnerable)
query = f"INSERT INTO secrets (name, value, owner) VALUES ('{secret.name}', '{secret.value}', '{secret.owner}')"
conn.execute(query)

# AFTER (safe)
conn.execute(
    "INSERT INTO secrets (name, value, owner) VALUES (?, ?, ?)",
    (secret.name, secret.value, secret.owner),
)
```

All four SQL statements in `main.py` need this treatment.

### Expected solution — hardcoded token

```python
# BEFORE
ADMIN_TOKEN = "supersecret-admin-token-1234"

# AFTER
import os
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]  # fail-fast; no default
```

Bonus: use `python-dotenv` for local dev, inject via Kubernetes Secret or Vault in production.

### Expected solution — timing-safe comparison

```python
import secrets as _secrets

def _verify_token(provided: str | None) -> bool:
    if not provided:
        return False
    return _secrets.compare_digest(provided, ADMIN_TOKEN)
```

**Strong answer:** Candidate makes all changes confidently, explains *why* parameterised queries
work (driver escaping, query plan separation), and raises that the fix for the hardcoded token
needs a deployment process change — not just a code change.

**Probe questions:**
- "An ORM like SQLAlchemy would also fix the injection — what are the trade-offs vs raw sqlite3?"
- "Where should `ADMIN_TOKEN` live in a Kubernetes deployment? Walk us through the secret lifecycle."
- "What's `secrets.compare_digest` and why does it matter here?"

---

## Section 3 — Test Suite: Find, Fix, Extend (15 min)

### Prompt
> "Open `test_main.py`. There are broken tests and dangerous gaps. Fix the broken ones, then add
> at least two new tests that a security-conscious engineer would consider essential."

### Broken tests to fix

**`test_create_secret_no_auth`** — asserts 200 but should assert 403:
```python
def test_create_secret_no_auth():
    response = client.post(
        "/secrets",
        json={"name": "x", "value": "y", "owner": "z"},
    )
    assert response.status_code == 403
```

**`test_delete_secret`** — the `pass` means it never fails even if deletion is broken:
```python
def test_delete_secret():
    # first create something to delete
    client.post("/secrets", json={"name": "temp", "value": "v", "owner": "o"},
                headers={"x-token": VALID_TOKEN})
    response = client.delete("/secrets/temp", headers={"x-token": VALID_TOKEN})
    assert response.status_code == 200
    # verify it's actually gone
    get_resp = client.get("/secrets/temp", headers={"x-token": VALID_TOKEN})
    assert get_resp.status_code == 404
```

**`test_get_secret` / `test_create_secret` ordering** — tests must be independent (use fixtures):
```python
@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_secrets.db")
    monkeypatch.setenv("DB_PATH", db_file)
    import main
    monkeypatch.setattr(main, "DB_PATH", db_file)
    main.init_db()
    yield
```

### New security tests (candidate should propose at least two)

```python
def test_sql_injection_in_get():
    """Secret name containing SQL metacharacters must not cause an error or leak data."""
    payload = "' OR '1'='1"
    response = client.get(f"/secrets/{payload}", headers={"x-token": VALID_TOKEN})
    assert response.status_code == 404   # not 200 with leaked rows, not 500

def test_list_secrets_requires_auth():
    """GET /secrets must not be publicly accessible."""
    response = client.get("/secrets")
    assert response.status_code in (401, 403)

def test_admin_run_not_accessible():
    """POST /admin/run should not exist in production; at minimum must reject bad tokens."""
    response = client.post("/admin/run", params={"cmd": "id"})
    assert response.status_code == 403

def test_secret_value_not_logged(caplog):
    """Secret values must never appear in application logs."""
    import logging
    with caplog.at_level(logging.DEBUG):
        client.get("/secrets/db_password", headers={"x-token": VALID_TOKEN})
    assert "hunter2" not in caplog.text
```

**Strong answer:** Candidate isolates tests with fixtures, understands that test ordering
dependency is a reliability bug (not just style), and independently proposes the SQL injection and
logging tests without being prompted.

**Probe questions:**
- "What's the difference between a unit test and an integration test for this service?"
- "How would you add these tests to a CI/CD pipeline? What stage should security tests run in?"
- "pytest has `caplog` — what built-in Python feature makes that possible?"

---

## Section 4 — Design / Problem Solving (5 min)

### Prompt
> "The team wants to replace the SQLite backend with a proper secrets vault. Walk us through how
> you'd design the migration without downtime, and what new security controls you'd add."

### What we're listening for

- **Zero-downtime migration pattern:** feature flag / dual-write → read from new → cut over → remove old
- **Vault integration:** HashiCorp Vault, AWS Secrets Manager, or GCP Secret Manager — dynamic
  secrets, lease/renewal, audit log
- **Auth upgrade:** replace static token with short-lived JWT or mTLS; integrate with an IdP (OIDC)
- **Threat modelling mindset:** "Who can read secrets? Who can list names? Can a pipeline token read
  *all* secrets, or only its own?" → principle of least privilege
- **Observability:** every secret access should emit an audit event (who, what, when, from where)

**Disqualifying gaps:** Candidate does not mention audit logging, or proposes a migration that
requires a maintenance window for a service already used by CI/CD.

---

## Scoring Rubric

| Dimension | Weight | Indicators |
|---|---|---|
| Security depth | 35% | Finds all Critical + High findings; uses OWASP vocabulary |
| Python/FastAPI fluency | 25% | Parameterised queries, env vars, `secrets` module, pytest fixtures |
| Testing rigour | 20% | Fixes broken tests, adds security-focused tests, isolation via fixtures |
| Communication | 10% | Explains risk in business terms; structures findings by severity |
| System design | 10% | Zero-downtime migration; principle of least privilege; audit logging |

### Hire signals
- Immediately spots `shell=True` + user-controlled input as RCE, not just "bad practice"
- Proposes `secrets.compare_digest` unprompted
- Adds the log-scrubbing test (`caplog`) without being asked
- Frames every finding in terms of blast radius for a *secrets management* service

### No-hire signals
- Misses SQL injection or dismisses it as "low risk because it's internal"
- Cannot write parameterised queries from memory
- Leaves `shell=True` endpoint in place after "fixing" the service
- Tests pass but have no assertions (accepts the existing `pass` in `test_delete_secret`)
