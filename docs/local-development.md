# Local development

## Requirements

Docker with Compose v2, and Python 3.12+ if you want to run tests or services
outside containers. Nothing else. No local PostgreSQL, no local Redis.

Resource use with everything running: roughly 1 GB of RAM. One PostgreSQL, one
Redis, one process per service plus workers.

## First run

```bash
cp .env.example .env     # or `make env`, which generates a JWT secret
make up
make health
```

`make up` builds images, starts PostgreSQL and Redis, waits for their health
checks, runs each service's migrations as a one-shot container, then starts the
services. The ordering is enforced by `depends_on` with
`service_completed_successfully`, so a service never starts against an
un-migrated database — which is the failure that usually looks like a mysterious
`relation does not exist` several seconds after boot.

First build takes a couple of minutes. Subsequent builds reuse the layer cache;
`libs/chirp-common` is copied before service code in each Dockerfile so that
editing a route does not reinstall the shared library.

`make env` is worth using: `.env.example` ships an obviously-invalid
`JWT_SECRET`, and `make env` replaces it with a real random value. Nothing will
start without one.

## Verifying it works

```bash
curl -s localhost:8001/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"ada@example.com","username":"ada",
       "display_name":"Ada Lovelace","password":"analytical-engine-1843"}'
```

One call, and the interesting path runs end to end: auth writes the account,
calls the user service over HTTP to create the profile, activates the account,
publishes `user.registered`, returns a token pair. Then:

```bash
TOKEN=$(curl -s localhost:8001/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"ada@example.com","password":"analytical-engine-1843"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s localhost:8002/api/v1/users/me -H "authorization: Bearer $TOKEN"
```

The second call goes to a service that has never spoken to the auth service and
has no session store. It verified the token locally.

Browsable API docs: <http://localhost:8001/docs>, <http://localhost:8002/docs>.

## Everyday commands

```bash
make up          make down        make clean     # clean also drops volumes
make logs        make ps          make health
make test        make test-integration
make lint        make format
make migrate     make seed SIZE=small
make metrics
```

`make clean` deletes the PostgreSQL volume. That is how you get a fresh
database when a migration goes sideways during development.

## Reading the logs

Logs are single-line JSON. Every line carries `request_id`, `correlation_id`,
`service` and `actor_id` where there is one — injected from ContextVars by a
logging filter, so no call site has to pass them around.

```bash
make logs | grep '"correlation_id":"01J8ZC..."'   # one causal chain, all services
docker compose logs -f auth | grep '"level":"ERROR"'
LOG_JSON=false docker compose up auth              # human-readable instead
```

The correlation id is the thing to reach for. A registration produces log lines
in two services and an event consumed in a third; they all share one
correlation id, so a single grep gives you the whole story in order.

## Running a service outside Docker

Useful for a debugger or a fast edit loop.

```bash
make install            # editable installs of chirp-common and both services
docker compose up -d postgres redis

cd services/auth
export DATABASE_URL="postgresql+asyncpg://chirp:chirp-local-password@localhost:5432/chirp_auth"
export REDIS_URL="redis://localhost:6379/0"
export EVENT_BUS_URL="redis://localhost:6379/1"
export JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export USER_SERVICE_URL="http://localhost:8002"
uvicorn app.main:app --reload --port 8001
```

Note the hostname change: inside Compose it is `postgres` and `redis`, outside
it is `localhost`. And if you generate a fresh `JWT_SECRET` here, tokens minted
by this process will not verify in the containerised services — use the value
from `.env` when you want them to interoperate.

Run a worker the same way: `python -m app.worker`.

## Configuration

Everything comes from environment variables; nothing is read from a file at
runtime. Compose loads `.env`; Kubernetes would supply the same names from
ConfigMaps and Secrets. `.env` is gitignored and `.env.example` contains no
real secrets.

Settings classes live in `app/settings.py` per service and compose mixins from
`chirp_common.config`. Adding a variable means adding a typed field — Pydantic
validates at startup, so a malformed value fails the boot loudly instead of
raising a `TypeError` inside a request two hours later.

The variables worth knowing:

| Variable | Effect |
|---|---|
| `JWT_SECRET` | Must match across all services. Minimum 16 chars |
| `DATABASE_URL` | Per service. `postgresql+asyncpg://...` |
| `REDIS_URL` | db 0 — cache and rate limiting |
| `EVENT_BUS_URL` | db 1 — event streams |
| `EVENT_BUS_BACKEND` | `redis` or `memory` (tests only) |
| `CACHE_ENABLED` | `false` forces every read to the database. Useful for proving the cache is not load-bearing |
| `LOG_JSON` | `false` for human-readable logs |
| `DB_ECHO` | `true` logs every SQL statement. Noisy; good for hunting N+1s |

## Metrics

```bash
curl -s localhost:8001/metrics | grep chirp_
```

All metrics are prefixed `chirp_` on a custom registry — no default Python GC
collectors cluttering the output. HTTP metrics are labelled with the **route
template** (`/api/v1/users/{username}`), not the resolved path, so a million
distinct usernames produce one time series rather than a million. That mistake
is the classic way to take down a Prometheus.

Nothing requires Prometheus to be running. The endpoint is just a page of text.

## Adding a service

The shape is fixed, which is the point — the third service you read takes a
minute. Copy `services/user` and work through:

1. `pyproject.toml` — name, and the `chirp-common` path dependency.
2. `app/settings.py` — a settings class with the service name, port and its own
   configuration.
3. `app/models.py` — tables this service owns. Import `ProcessedEvent` if it
   consumes events, so the table lands in this service's metadata.
4. `migrations/` — copy `env.py` and `script.py.mako`, then
   `alembic revision --autogenerate -m "initial"`, then **read what it
   generated**.
5. `app/repository.py` — SQL only. `app/service.py` — domain logic, no SQL and
   no HTTP. `app/routes.py` — HTTP only, no logic.
6. `app/dependencies.py` — the composition root. Everything is constructed here
   and injected; nothing reaches for a module-level singleton.
7. `app/main.py` — `create_app` with health checks registered.
8. `app/worker.py` if it consumes events.
9. `tests/` — copy `conftest.py`; it gives you an in-memory SQLite database, an
   in-memory event bus and a token factory.
10. `Dockerfile` — copy verbatim, change the service directory.
11. `docker-compose.yml` — the service, its `-migrate` one-shot, and its worker.
12. `docker/postgres/10-create-databases.sh` already creates all ten databases.

Then add it to `docs/services.md` and the README status table.

## Troubleshooting

**`relation "x" does not exist`** — migrations did not run. `docker compose logs
auth-migrate`. After editing a migration, `make clean && make up`.

**`JWT_SECRET` validation error at startup** — `.env` is missing or still has
the placeholder. `make env`.

**401 on a request with a token that just worked** — access tokens last 15
minutes. Refresh, or check the two processes are using the same `JWT_SECRET`.

**Events are published but nothing consumes them** — the worker is a separate
container. `docker compose ps user-worker`, then `docker compose logs
user-worker`. A consumer group only receives messages added after it was
created, so events published before the worker's first start are not delivered
to it.

**Counters are wrong after a crash** — expected; see
[failure-modes.md](failure-modes.md). Counters are a projection, not truth.

**Port already in use** — 5432 and 6379 are published for host access. Change
the left-hand side of the port mapping if you have local instances running.

**`docker compose up` hangs on a health check** — `docker compose ps` shows
which container is unhealthy. PostgreSQL's check verifies that
`chirp_moderation` exists, so it stays unhealthy until the init script has
created all ten databases, which is correct but slow on first boot.
