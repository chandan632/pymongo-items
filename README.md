# pymongo-items

FastAPI + MongoDB inventory API. Companion UI: [`next-items`](../next-items).

## Included

| Area | Implementation |
|------|----------------|
| Auth | JWT access tokens, HttpOnly refresh cookies, CSRF double-submit, Argon2 passwords |
| Roles | `viewer` / `editor` / `admin` |
| Items | CRUD, filter, sort, search, pagination |
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
│   ├── services/
│   ├── routes/             # auth, items, health
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
| `GET /api/v1/health` | Liveness |
| `GET /api/v1/ready` | Readiness |

Passwords require upper, lower, and a digit (8–128 chars).

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

See `.env.example` for the full list. Important variables:

| Variable | Purpose |
|----------|---------|
| `MONGO_URI` / `MONGO_DB_NAME` | Database |
| `MONGO_*_POOL_*` | Connection pool |
| `USE_REDIS` / `REDIS_URL` | Shared store for multi-worker |
| `CORS_ORIGINS` | Frontend origins |
| `API_PREFIX` | Default `/api/v1` |
| `JWT_*` | Access token signing |
| `COOKIE_*` / `REFRESH_COOKIE_*` / `CSRF_*` | Cookie + CSRF contract |
| `RATE_LIMIT_*` / `EXPORT_MAX_ROWS` | Abuse controls |
| `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_*` | Login lockout |
| `ENVIRONMENT` / `ALLOW_SEED` | Runtime mode |
| `TRUSTED_PROXIES` | Clients allowed to set `X-Forwarded-For` |

## Auth

| Concern | Approach |
|---------|----------|
| Access | Short-lived JWT in response body (SPA keeps it in memory) |
| Refresh | HttpOnly cookie; rotated on use; hash stored server-side |
| CSRF | Readable cookie + `X-CSRF-Token` on refresh/logout |
| Lockout | Failures per email+IP; refresh reuse revokes the session family |
| Headers | Frame deny, CSP, nosniff, HSTS in production |

Response envelope:

```json
{ "success": true, "data": {}, "meta": {}, "request_id": "..." }
```

```json
{ "success": false, "error": { "code": "BAD_REQUEST", "message": "..." }, "request_id": "..." }
```

Flow: `POST /auth/login` → Bearer access on APIs → `POST /auth/refresh` (CSRF) → `POST /auth/logout`. Admins register users via `POST /auth/register`.

## API (`API_PREFIX`, default `/api/v1`)

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| `GET` | `/health` | — | Liveness |
| `GET` | `/ready` | — | Mongo (+ Redis if enabled) |
| `POST` | `/auth/login` | — | Login |
| `POST` | `/auth/refresh` | — | Refresh access token |
| `POST` | `/auth/logout` | — | Logout |
| `GET` | `/auth/me` | viewer | Current user |
| `POST` | `/auth/register` | admin | Create user |
| `GET` | `/items/` | viewer | List |
| `POST` | `/items/` | editor | Create |
| `GET` | `/items/{id}` | viewer | Get one |
| `PATCH` | `/items/{id}` | editor | Update |
| `DELETE` | `/items/{id}` | editor | Delete |
| `POST` | `/items/bulk` | editor | Bulk actions |
| `GET` | `/items/export` | viewer | CSV export |
| `POST` | `/items/seed` | admin | Seed sample data |

List query params: `page`, `page_size` (≤ 500), `sort_by`, `sort_order`, `q`, `status`, `category`, `min_price`, `max_price`, `min_quantity`, `max_quantity`.

- **Bulk**: `delete` \| `set_status` \| `adjust_quantity`; scope via `ids` or `select_all` + list filters.
- **Export**: capped by `EXPORT_MAX_ROWS`.
- **Idempotency**: `Idempotency-Key` on mutating methods; replays set `X-Idempotent-Replay: true`.
- **Pagination**: `skip`/`limit` slows on very deep pages. Unfiltered totals use `estimated_document_count`; filtered lists use `count_documents`.

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
- Keep Mongo/Redis bound to localhost in compose.
- Leave `TRUSTED_PROXIES` empty unless TLS terminates at a known proxy.
