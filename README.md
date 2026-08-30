# pymongo-items

FastAPI + MongoDB inventory API. Companion UI: [`next-items`](../next-items).

## Included

| Area | Implementation |
|------|----------------|
| Auth | JWT access tokens, HttpOnly refresh cookies, CSRF (`csrf_token` in login/refresh body + header), Argon2id passwords |
| Users | Admin user management (list/create/edit role/active/delete/reset password); users change own password |
| Roles | `viewer` / `editor` / `admin`; role or inactive change forces re-login |
| Items | CRUD, filter, sort, search, **cursor** pagination |
| Bulk | Delete, set status, adjust quantity (ids or select-all + filters) |
| Export | Streaming CSV with injection sanitization and row cap |
| Seed | Optional sample data (`ALLOW_SEED`, admin only) |
| Ops | Rate limits, idempotency keys, request IDs, structured logs |
| Health | `GET /api/v1/health` (liveness), `GET /api/v1/ready` (Mongo; Redis if enabled) |
| Quality | Ruff, mypy, pytest + coverage, pre-commit, GitHub Actions CI |

## Stack

| Piece | Choice |
|-------|--------|
| Runtime | Python 3.12+, FastAPI, Uvicorn |
| Database | MongoDB 8 (async PyMongo) |
| Store | In-memory or Redis (rate limit, idempotency, refresh tokens) |
| Config | pydantic-settings + `.env` |
| Packaging | `uv` |

## Layout

```
pymongo-items/
├── docker-compose.yml      # Mongo + Redis (+ optional API profile)
├── Dockerfile
├── .env.example
├── pyproject.toml
├── src/items_api/
│   ├── main.py             # app lifespan, middleware, routers
│   ├── config.py
│   ├── db.py
│   ├── cli.py              # create-admin
│   ├── api/                # deps, response helpers
│   ├── models/
│   ├── repositories/
│   ├── services/           # auth, items, seed, cursor, user_admin
│   ├── routes/             # auth, users, items, health
│   ├── middleware/
│   ├── security/
│   └── stores/
└── tests/
```

## Quick start

Requirements: Python 3.12+, Docker, [`uv`](https://docs.astral.sh/uv/).

### Fresh local run (API + UI)

```bash
# free app/db ports (and stop host Docker proxies if Desktop can't bind 6379/27017)
fuser -k 8000/tcp 3000/tcp 6379/tcp 27017/tcp 2>/dev/null || true
DOCKER_HOST=unix:///var/run/docker.sock docker stop \
  $(DOCKER_HOST=unix:///var/run/docker.sock docker ps -q --filter publish=6379 --filter publish=27017) 2>/dev/null || true

# backend: recreate Mongo/Redis volumes (omit -v to keep existing data)
cd /home/chandan/workspace/Items/pymongo-items
docker compose down -v
docker compose up -d mongo redis

cp --update=none .env.example .env
uv sync --extra dev
uv run create-admin admin@example.com 'AdminPass123'
uv run items-api
```

In a **second** terminal (UI):

```bash
cd /home/chandan/workspace/Items/next-items
cp --update=none .env.example .env.local
npm ci
npm run dev
```

Optional checks:

```bash
curl -s http://localhost:8000/api/v1/health
curl -s http://localhost:8000/api/v1/ready
cd /home/chandan/workspace/Items/pymongo-items && uv run pytest -q
cd /home/chandan/workspace/Items/next-items && npm test
```

| URL | Purpose |
|-----|---------|
| http://localhost:8000 | API |
| http://localhost:8000/docs | OpenAPI (non-production) |
| http://localhost:3000 | UI — login `admin@example.com` / `AdminPass123` |
| http://localhost:3000/admin/users | Admin user management |
| http://localhost:3000/account/change-password | Change own password (any logged-in user) |
| `GET /api/v1/health` | Liveness |
| `GET /api/v1/ready` | Readiness |

Passwords require upper, lower, and a digit (8–128 chars). Admin-created users get `DEFAULT_USER_PASSWORD` from env until they change it.

### MongoDB (Robo 3T / Compass / Studio 3T)

Compose Mongo root user is `items` / `items_secret`. App database: `items_db`. Bound to `127.0.0.1` only — use `localhost`.

```
mongodb://items:items_secret@localhost:27017/?authSource=admin
```

| Field | Value |
|-------|--------|
| Type | Direct Connection |
| Address / Port | `localhost` / `27017` |
| Authentication | On |
| User Name | `items` |
| Password | `items_secret` |
| Auth DB | `admin` |
| Mechanism | SCRAM-SHA-256 (or SCRAM-SHA-1) |

Same URI is in `.env.example` as `MONGO_URI`. If an older unauthenticated volume exists, recreate it (`docker compose down -v`) or keep a matching `MONGO_URI`. Robo 3T is outdated for Mongo 8; prefer Compass or Studio 3T if connect fails.

If `docker compose up` fails with **address already in use** on `6379`/`27017`, another Docker engine (often system `dockerd` while the CLI uses Docker Desktop) still holds those ports — run the `DOCKER_HOST=… docker stop` line above, then `docker compose up -d mongo redis` again.

Optional: `uv run pre-commit install`

### Seed sample data

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"AdminPass123"}' \
  | python -c 'import sys,json; print(json.load(sys.stdin)["data"]["access_token"])')

curl -X POST http://localhost:8000/api/v1/items/seed \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: seed-1' \
  -d '{"count": 5000, "clear": true}'
```

### Full stack in Docker

```bash
docker compose --profile full up --build
```

## Production

```bash
export ENVIRONMENT=production ALLOW_SEED=false COOKIE_SECURE=true
export WEB_CONCURRENCY=4
uv run uvicorn items_api.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers

# or
docker build -t items-api .
docker run --rm -p 8000:8000 --env-file .env -e WEB_CONCURRENCY=4 items-api
```

Production refuses weak `JWT_SECRET`, `ALLOW_SEED=true`, and `COOKIE_SECURE=false`. Prefer Redis when `workers > 1`.

## Configuration

Copy `.env.example` → `.env`. These are **required** (no code defaults): `MONGO_URI`, `MONGO_DB_NAME`, `REDIS_URL`, `CORS_ORIGINS`, `JWT_SECRET`, `DEFAULT_USER_PASSWORD`. Other keys are optional overrides (see `.env.example`).

| Variable | Purpose |
|----------|---------|
| `MONGO_URI` / `MONGO_DB_NAME` | Database |
| `MONGO_*_POOL_*` | Connection pool |
| `USE_REDIS` / `REDIS_URL` | Shared store for multi-worker (`REDIS_URL` required even when `USE_REDIS=false`) |
| `CORS_ORIGINS` | Frontend origins (required) |
| `API_PREFIX` | Default `/api/v1` |
| `JWT_SECRET` | Access token signing (required) |
| `COOKIE_*` / `REFRESH_COOKIE_*` / `CSRF_*` | Cookie + CSRF contract |
| `DEFAULT_USER_PASSWORD` | Password for admin-created users / password reset (required; match UI `NEXT_PUBLIC_DEFAULT_USER_PASSWORD`) |
| `REFRESH_REUSE_GRACE_SECONDS` | Concurrent refresh tolerance after rotation (default `30`) |
| `RATE_LIMIT_*` / `EXPORT_MAX_ROWS` | Abuse controls |
| `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_*` | Login lockout |
| `ENVIRONMENT` / `ALLOW_SEED` | Runtime mode |
| `TRUSTED_PROXIES` | Clients allowed to set `X-Forwarded-For` |

## Auth

| Concern | Approach |
|---------|----------|
| Access | Short-lived JWT in response body (SPA keeps it in memory); includes `role` claim |
| Refresh | HttpOnly cookie; rotated on use; hash stored server-side |
| CSRF | Cookie + `X-CSRF-Token`; login/refresh also return `csrf_token` in JSON for cross-origin SPAs |
| Concurrent refresh | Within `REFRESH_REUSE_GRACE_SECONDS`, replaying the previous cookie returns the same successor (avoids logout on rapid reload) |
| Privilege change | Admin role/inactive updates revoke refresh sessions; next API call with stale JWT role → `401 PRIVILEGES_CHANGED` / `ACCOUNT_INACTIVE` |
| Passwords | Argon2id one-way hashes only (`password_hash`); never returned by API |
| Lockout | Failures per email+IP; reuse after grace window revokes the session family |
| Headers | Frame deny, CSP, nosniff, HSTS in production |

Response envelope:

```json
{ "success": true, "data": {}, "meta": {}, "request_id": "..." }
```

```json
{ "success": false, "error": { "code": "BAD_REQUEST", "message": "..." }, "request_id": "..." }
```

Flow: `POST /auth/login` → Bearer access on APIs → `POST /auth/refresh` (CSRF) → `POST /auth/logout`.  
Users: `POST /auth/change-password` (self). Admins: `/auth/users` CRUD + reset, or the UI **Users** page.

## API (`API_PREFIX`, default `/api/v1`)

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| `GET` | `/health` | — | Liveness |
| `GET` | `/ready` | — | Mongo (+ Redis if enabled) |
| `POST` | `/auth/login` | — | Login (returns `access_token`, `user`, `csrf_token`) |
| `POST` | `/auth/refresh` | — | Refresh access token (+ new `csrf_token`) |
| `POST` | `/auth/logout` | — | Logout |
| `GET` | `/auth/me` | viewer | Current user |
| `POST` | `/auth/change-password` | viewer | Change own password; clears cookies / sessions |
| `POST` | `/auth/register` | admin | Create user (custom password) |
| `GET` | `/auth/users` | admin | List users |
| `POST` | `/auth/users` | admin | Create user (default password) |
| `PATCH` | `/auth/users/{id}` | admin | Update role / active status (revokes target sessions on role/deactivate) |
| `DELETE` | `/auth/users/{id}` | admin | Delete user |
| `POST` | `/auth/users/{id}/reset-password` | admin | Reset password to default |
| `GET` | `/items/` | viewer | List (cursor pagination) |
| `POST` | `/items/` | editor | Create |
| `GET` | `/items/{id}` | viewer | Get one |
| `PATCH` | `/items/{id}` | editor | Update |
| `DELETE` | `/items/{id}` | editor | Delete |
| `POST` | `/items/bulk` | editor | Bulk actions |
| `GET` | `/items/export` | viewer | CSV export |
| `POST` | `/items/seed` | admin | Seed sample data |

List query params: `cursor` (optional), `page_size` (≤ 500), `sort_by`, `sort_order`, `q`, `status`, `category`, `min_price`, `max_price`, `min_quantity`, `max_quantity`.

List `meta`: `{ "page_size", "total", "has_more", "next_cursor" }`.

- **Bulk**: `delete` \| `set_status` \| `adjust_quantity`; scope via `ids` or `select_all` + list filters.
- **Export**: capped by `EXPORT_MAX_ROWS`.
- **Idempotency**: `Idempotency-Key` on mutating methods; replays set `X-Idempotent-Replay: true`.
- **Pagination**: keyset/cursor on `(sort_by, _id)`. Unfiltered totals use `estimated_document_count`; filtered lists use `count_documents`.

## Development

```bash
docker compose up -d mongo redis
uv sync --extra dev
uv run ruff check .
uv run mypy src/items_api
uv run pytest --cov
```

Tests use `items_db_test` (dropped after the suite). Coverage fail-under is set in `pyproject.toml`.

## Security checklist

- Rotate `JWT_SECRET` and Mongo credentials before shared or production use.
- Set `ENVIRONMENT=production`, `ALLOW_SEED=false`, `COOKIE_SECURE=true` behind HTTPS.
- Change `DEFAULT_USER_PASSWORD` in non-local environments.
- Keep Mongo/Redis bound to localhost in compose.
- Leave `TRUSTED_PROXIES` empty unless TLS terminates at a known proxy.
