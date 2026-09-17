# Chirp

A lightweight X-like social platform built as real microservices, intended as a
**workload you deploy and operate yourself**. The application code, service
boundaries, APIs, schemas, events, tests and local development environment are
here. AWS, Terraform, Kubernetes, ingress, autoscaling, tracing backends and
load testing are deliberately *not* here — that is the half of the system this
repository is designed to be the input to.

---

## Status

This repository is being built in stages. What exists today is the platform
spine plus the two services every other one depends on.

| Component | State |
|---|---|
| `libs/chirp-common` — config, logging, context, errors, HTTP factory, DB, cache, rate limiting, event bus, metrics, idempotency | Complete |
| `services/auth` — credentials, sessions, token issuance and rotation | Complete, 25 tests |
| `services/user` — profiles, usernames, counters, event projector | Complete, 19 tests |
| Docker Compose, migrations, seed data, docs | Complete for the above |
| `post`, `graph`, `timeline`, `search`, `notification`, `messaging`, `media`, `moderation`, `gateway`, web frontend | Not yet built — see [docs/roadmap.md](docs/roadmap.md) |

Everything listed as complete runs, has migrations, has a Dockerfile, has a
health and metrics endpoint, and is covered by tests that assert behaviour
rather than existence. Nothing is a scaffold or a `TODO`.

## Quick start

```bash
cp .env.example .env          # or: make env  (generates a JWT secret for you)
make up                       # build and start everything
make health                   # readiness of each service
```

Then:

```bash
curl -s localhost:8001/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"ada@example.com","username":"ada",
       "display_name":"Ada Lovelace","password":"analytical-engine-1843"}'
```

That single call exercises the interesting path: the auth service writes
credentials, calls the user service over HTTP to create the profile, activates
the account, publishes `user.registered` to Redis Streams and returns a token
pair. Watch it happen with `make logs` — every line carries the same
`correlation_id`.

Interactive API docs: <http://localhost:8001/docs> and <http://localhost:8002/docs>.

## Running the tests

```bash
make install    # shared library + services in editable mode
make test       # unit suites, SQLite, no containers required
```

`make test-integration` runs the same suites against the PostgreSQL in Compose.
The unit suites use SQLite for speed; the differences that matters (timezone
handling, `ON CONFLICT ... RETURNING`) are called out in
[docs/testing.md](docs/testing.md).

## Generating data

```bash
make seed SIZE=small     # 200 users
make seed SIZE=large     # 50 000 users
```

The seed script writes straight into each service's database on purpose — it
exists to produce load-test volumes, and HTTP would be the bottleneck. See the
docstring in `scripts/seed.py`.

## Layout

```
libs/chirp-common/     shared platform code; no business logic
services/<name>/       one service: app/, tests/, migrations/, Dockerfile
docker/                container support files (PostgreSQL init)
scripts/               development tooling (seeding)
docs/                  architecture, decisions, failure modes, scalability
```

Every service follows the same shape, so the third one you read takes a minute:

```
services/auth/
  app/
    main.py          create_app + lifespan
    settings.py      environment-derived configuration
    dependencies.py  composition root; everything injected from here
    routes.py        HTTP surface only, no logic
    service.py       domain logic, no SQL, no HTTP
    repository.py    SQL only
    models.py        tables this service owns
    schemas.py       request/response contracts
    worker.py        event consumers (separate process)
  migrations/        this service's own Alembic history
  tests/
```

## Documentation

| Document | What it answers |
|---|---|
| [architecture.md](docs/architecture.md) | How the pieces fit and why the boundaries are where they are |
| [services.md](docs/services.md) | Each service's responsibility, data and dependencies |
| [api.md](docs/api.md) | Conventions: versioning, errors, pagination, auth |
| [database.md](docs/database.md) | Ownership, schemas, indexes, migrations |
| [events.md](docs/events.md) | The bus, the envelope, delivery guarantees, the catalogue |
| [local-development.md](docs/local-development.md) | Running, debugging, adding a service |
| [testing.md](docs/testing.md) | What is tested and how to run it |
| [scalability.md](docs/scalability.md) | What breaks first at 10K, 100K and 1M users |
| [failure-modes.md](docs/failure-modes.md) | What happens when each dependency dies |
| [decisions.md](docs/decisions.md) | The choices worth arguing about, and the alternatives |
| [roadmap.md](docs/roadmap.md) | What is left to build and in what order |

## What this repository will not do for you

No Terraform, no Helm charts, no Kubernetes manifests, no EKS/VPC/ALB/RDS
configuration, no CloudFront, no Route 53, no Prometheus or Grafana
deployment, no load testing, no cost modelling. The application is built to
make that work possible — every service is independently runnable, configured
entirely through environment variables, stateless apart from its own database,
health-checked on separate liveness and readiness endpoints, and exposes
Prometheus metrics — but the deployment architecture is yours.
