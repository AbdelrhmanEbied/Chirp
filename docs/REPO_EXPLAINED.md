# Chirp -- Complete Repository Guide

## What This Is

Chirp is a lightweight X/Twitter-like social platform built as a **microservices architecture** in Python. It is designed to be a workload you deploy and operate yourself. The repository contains the application code, service boundaries, APIs, schemas, events, tests, and local development environment -- but deliberately excludes infrastructure (AWS, Terraform, Kubernetes, ingress, autoscaling, tracing).

**Current status:** 2 of 11 planned services are built and tested (44 tests total). The two foundational services -- auth and user -- are complete. The remaining 9 services (post, graph, timeline, search, notification, messaging, media, moderation, gateway) plus a web frontend are planned.

---

## Repository Structure

```
1M-USER/
├── libs/
│   └── chirp-common/          # Shared platform library (no business logic)
├── services/
│   ├── auth/                   # Authentication service (port 8001) -- BUILT
│   └── user/                   # User profile service (port 8002) -- BUILT
├── docker/
│   └── postgres/               # DB init scripts (creates 10 databases)
├── scripts/
│   └── seed.py                 # Development data generator (200 or 50K users)
├── docs/                       # 11 architecture/decision documents
├── docker-compose.yml          # Local dev topology
├── Makefile                    # Developer entry points
├── pyproject.toml              # Root lint/type config (ruff, mypy, pytest)
└── .env.example                # Environment variable template
```

Every service follows an identical internal shape:

```
services/<name>/
  app/
    main.py          # create_app + lifespan
    settings.py      # Environment-derived configuration (Pydantic)
    dependencies.py  # Composition root; everything injected from here
    routes.py        # HTTP surface only, no logic
    service.py       # Domain logic, no SQL, no HTTP
    repository.py    # SQL only
    models.py        # SQLAlchemy tables this service owns
    schemas.py       # Pydantic request/response contracts
    worker.py        # Event consumers (separate process)
  migrations/        # Alembic history (one per service)
  tests/             # Behavior-focused test suites
  Dockerfile         # Per-service container build
```

---

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.12+ | Async/await, type hints, fast iteration |
| Web framework | FastAPI | Async, auto-generated OpenAPI, dependency injection |
| ORM | SQLAlchemy (async) | Mature, async sessions, Alembic integration |
| Database | PostgreSQL 16 | JSON, CTEs, strong consistency, production-proven |
| Cache | Redis 7 | Fast, already needed for rate limiting and events |
| Event bus | Redis Streams | Zero new containers, consumer groups, per-entry pending lists |
| Auth | JWT (HS256) | Stateless verification by every service, no central auth hop |
| Password hashing | Argon2id | Memory-hard, modern |
| ID generation | ULID | Lexicographically sortable, creation-time-ordered, cross-service |
| Testing | pytest + httpx | Async, HTTP-level tests against real ASGI app |
| Linting | Ruff + mypy | Fast lint, strict-ish types |
| Migrations | Alembic | One history per service, run as one-shot containers |

---

## The Two Built Services

### Auth Service (port 8001)

**Responsibility:** Proving that a request comes from a particular user. Nothing else.

**Data it owns:**
- `accounts` -- email, Argon2id password hash, admin flag, activation timestamp, soft delete
- `sessions` -- one row per logged-in device (SHA-256 of refresh token, expiry, revocation, rotation chain)

**Key endpoints:**
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account + sign in (201 with token pair) |
| POST | `/api/v1/auth/login` | Exchange credentials for tokens |
| POST | `/api/v1/auth/refresh` | Rotate refresh token; reuse = theft detection |
| POST | `/api/v1/auth/logout` | Revoke one refresh token (204) |
| POST | `/api/v1/auth/logout-all` | Revoke every session except current |
| GET | `/api/v1/auth/me` | Current account (email, admin flag) |
| GET | `/api/v1/auth/sessions` | Active devices |
| POST | `/api/v1/auth/password` | Change password, revoke all sessions |

**Critical design choices:**
1. Auth is **not on the hot path** of any request except login. Every other service verifies tokens locally with the shared secret. This makes auth the smallest deployment.
2. Login returns the **same error** for unknown email and wrong password. The unknown-email path still runs a hash verification against a dummy hash so timing matches (prevents email enumeration).
3. Refresh tokens are **opaque random strings**, not JWTs. They rotate on every use; presenting an already-rotated token revokes every session for the account (theft detection).
4. `activated_at = NULL` on a new account means the profile creation handshake didn't complete. The account cannot log in until it's set. This is how the system survives the user service being down mid-registration without a distributed transaction.

**Publishes:** `user.registered`

**Consumes:** Nothing.

---

### User Service (port 8002)

**Responsibility:** Who a user publicly is, and the cheap aggregate numbers shown next to that.

**Data it owns:**
- `user_profiles` -- username, display name, bio, location, website, avatar/banner media IDs, denormalised follower/following/post counts
- `username_history` -- released handles (prevents impersonation after username change)
- `processed_events` -- idempotency ledger for event consumption

**Key endpoints:**
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/users/me` | Own profile |
| PATCH | `/api/v1/users/me` | Edit profile fields |
| PUT | `/api/v1/users/me/username` | Change username (30-day cooldown) |
| PUT | `/api/v1/users/me/media` | Set avatar/banner media IDs |
| DELETE | `/api/v1/users/me` | Soft delete account |
| GET | `/api/v1/users/search` | Prefix username search |
| GET | `/api/v1/users/{username}` | Public profile |
| POST | `/internal/v1/users` | Create profile (called by auth during registration) |
| POST | `/internal/v1/users/summaries` | Batch hydration (the N+1 antidote) |

**Critical design choices:**
1. Counters (followers_count, etc.) are **denormalised projections**, not live queries. A consumer keeps them in step with graph/post events. They can drift; the follow edge is the source of truth.
2. `POST /internal/v1/users/summaries` exists specifically so callers never loop over IDs issuing one request each -- N+1 over a network is an outage, not a performance problem.
3. Profile reads are **cached in Redis** (invalidated on write). A cold cache costs latency, not correctness.
4. Username changes park the old handle in `username_history` so nobody can claim it and inherit mentions.

**Publishes:** `user.profile_updated`, `user.deleted`

**Consumes:** `graph.user_followed`, `graph.user_unfollowed`, `post.created`, `post.deleted` (each adjusting counters, guarded by idempotent claim)

---

## Shared Library: chirp-common

This is the platform spine. No business logic lives here -- only cross-cutting concerns that every service needs:

| Module | Purpose |
|---|---|
| `config` | Pydantic settings mixins (Database, Redis, EventBus, Service) |
| `logging` | Structured JSON logging with automatic request/correlation ID injection |
| `context` | ContextVar-based ambient context (request_id, correlation_id, actor_id) |
| `errors` | Typed exception hierarchy (AppError, ConflictError, NotFoundError, etc.) |
| `http/app` | FastAPI application factory -- identical middleware order, error envelope, health/metrics endpoints for every service |
| `http/client` | Service-to-service HTTP client with timeouts, retries with jitter, circuit breaker, correlation ID propagation |
| `http/middleware` | RequestContextMiddleware, AccessLogMiddleware, BodySizeLimitMiddleware |
| `db/session` | Async SQLAlchemy engine + session factory with pool tuning, statement timeouts, health checks |
| `db/base` | SQLAlchemy declarative base, ULID primary key mixin, timestamp mixin, soft delete mixin |
| `auth/jwt` | JWT codec (issue + verify), designed for RS256 upgrade |
| `auth/deps` | FastAPI dependency for extracting the authenticated user from the token |
| `events/bus` | Broker-agnostic EventBus protocol (Redis Streams is the local impl) |
| `events/envelope` | EventEnvelope (ULID id, type, version, producer, subject_id, actor_id, correlation_id, causation_id, payload) |
| `events/worker` | EventWorker with consumer groups, pending list claiming, dead-letter queue, exponential backoff |
| `events/redis_streams` | Redis Streams implementation of EventBus |
| `events/memory` | In-memory EventBus for tests |
| `cache` | RedisCache (with fail-open on Redis errors) and NullCache (for tests) |
| `ratelimit` | Fixed-window counter in Redis (with fail-open) and NullRateLimiter |
| `idempotency` | `claim_event` -- transactional INSERT ... ON CONFLICT DO NOTHING for consumer deduplication |
| `metrics` | Prometheus counters/histograms/gauges on a custom registry (chirp_ prefix) |
| `security` | Password hashing (Argon2id), token generation, token hashing (SHA-256) |
| `ids` | ULID generation |
| `pagination` | Cursor-based keyset pagination (base64-encoded, versioned) |
| `timeutil` | UTC timezone helpers (bridging SQLite naive vs PostgreSQL aware datetimes) |

---

## Event System

### Architecture

One Redis Stream per event type (`chirp.events.post.created`). One consumer group per consuming service. One consumer name per process instance. Dead letters go to `chirp.events.dlq`.

### Event Envelope

Every event carries identical metadata:

| Field | Purpose |
|---|---|
| `id` | ULID -- deduplication key for idempotent consumers |
| `type` | EventType enum -- determines the stream |
| `version` | Payload schema version -- producers evolve independently |
| `producer` | Which service emitted it |
| `subject_id` | The aggregate the event is about |
| `actor_id` | The user who caused it |
| `occurred_at` | Consumers detect and discard out-of-order deliveries |
| `correlation_id` | Ties to the originating user request (flows through all hops) |
| `causation_id` | The request or event ID that directly produced this one |
| `payload` | Type-specific data |

### Guarantees

- **At-least-once.** Consumers must be idempotent.
- **Ordering per stream only.** No ordering across types.
- **Not transactional with the producer's DB write.** (Outbox pattern is the documented upgrade path.)

### Event Catalogue (implemented today)

| Event | Producer | Consumed by |
|---|---|---|
| `user.registered` | auth | (search, notification when built) |
| `user.profile_updated` | user | search, timeline cache invalidation |
| `user.deleted` | user | post, graph, search, timeline |
| `graph.user_followed` | graph | **user** (counters), timeline, notification |
| `graph.user_unfollowed` | graph | **user** (counters), timeline, notification |
| `post.created` | post | timeline, search, **user** (posts_count) |
| `post.deleted` | post | timeline, search, **user** |

### Consumer Pattern

```python
async def on_followed(event: EventEnvelope) -> None:
    async with context.database.session() as session:
        if not await claim_event(
            session, event_id=event.id, consumer=CONSUMER_GROUP,
            event_type=event.type.value,
        ):
            return  # already applied
        await repository.adjust_counter(event.subject_id, "followers_count", 1)
```

Rules: claim inside the same transaction as writes; never assume ordering across types; raise on failure; keep handlers short.

---

## Database Design

### Ownership Model

Each service owns its tables outright. **No service reads or writes another service's tables.** The only way to get another service's data is its API or its events.

### Local Topology

One PostgreSQL 16 container, ten logical databases (one per service):
```
chirp_auth  chirp_user  chirp_post  chirp_graph  chirp_timeline
chirp_search  chirp_notification  chirp_messaging  chirp_media  chirp_moderation
```

Created by `docker/postgres/10-create-databases.sh` on first start.

### Conventions

- **ULID primary keys** -- 26-character Crockford base32 strings, lexicographically sortable by creation time
- **Timestamps** -- `created_at` and `updated_at` on everything, always `TIMESTAMPTZ`, always UTC
- **Soft deletion** -- nullable `deleted_at` where content must survive deletion; every query filters `deleted_at IS NULL`
- **Naming** -- plural snake_case tables, `ix_<table>_<columns>` indexes, `ck_<table>_<rule>` constraints
- **No cross-service foreign keys** -- a profile row references `account.id` with no constraint enforcing it

### Schema: auth

- `accounts` -- id (ULID), email (unique), password_hash (Argon2id), is_admin, activated_at, last_login_at, deleted_at
- `sessions` -- id (ULID, appears in tokens as `sid`), account_id (FK to accounts), token_hash (SHA-256, unique), expires_at, revoked_at, rotated_to_id, user_agent, ip_address

### Schema: user

- `user_profiles` -- id (same as account id, no constraint), username (unique, lowercase), display_name, bio, location, website, avatar_media_id, banner_media_id, username_changed_at, followers_count, following_count, posts_count (all CHECK >= 0), deleted_at
- `username_history` -- id (ULID), user_id, username, released_at
- `processed_events` -- event_id (PK), consumer (PK), event_type, processed_at

### Migrations

Alembic, one history per service, run as a **one-shot container** before the service starts. Migrations never run inside the application process.

---

## API Conventions

### Versioning

Public routes: `/api/v1/<resource>`
Internal routes: `/internal/v1/<resource>` (service-to-service only, excluded from OpenAPI)

### Authentication

```
Authorization: Bearer <access_token>
```

JWT (HS256), verified locally by every service with the shared secret. Claims: `sub` (user ID), `sid` (session ID), `jti` (token ID), `iss`, `aud`, `exp`, `iat`, `scopes`.

**Key tradeoff:** an access token cannot be revoked before it expires (up to 15 minutes). Logging out revokes the refresh token, preventing new access tokens. The upgrade path is RS256 with a JWKS endpoint.

### Error Envelope

```json
{
  "error": {
    "code": "conflict",
    "message": "That username is taken.",
    "details": {"field": "username"},
    "request_id": "01J8ZC5K3Q7V2X9N4M6B8T1R0E"
  }
}
```

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `bad_request` / `invalid_cursor` | Malformed input |
| 401 | `unauthorized` | Missing/invalid/expired token |
| 403 | `forbidden` | Authenticated but not permitted |
| 404 | `not_found` | Doesn't exist, soft-deleted, or not yours |
| 409 | `conflict` | Unique constraint violation |
| 422 | `validation_error` | Field-level failure |
| 429 | `rate_limited` | Over limit; Retry-After header set |
| 502 | `dependency_error` | Downstream service failed |
| 503 | `service_unavailable` | Can't serve requests |
| 500 | `internal_error` | Unhandled (generic message only) |

### Pagination

Cursor-based keyset pagination on ULID primary keys. Cursors are opaque base64 strings. `limit` defaults to 20, capped at 100.

### Operational Endpoints (every service)

| Endpoint | Purpose |
|---|---|
| `GET /health/live` | Is process alive? Never touches dependencies |
| `GET /health/ready` | Can it serve? Checks dependencies; 503 if critical one is down |
| `GET /metrics` | Prometheus text format |
| `GET /docs` | Generated OpenAPI docs |

---

## Request Flow: Registration (The Interesting Path)

```
1. Client sends POST /api/v1/auth/register to auth service
2. Auth writes account (activated_at = NULL, cannot log in yet)
3. Auth calls POST /internal/v1/users on user service (synchronous HTTP)
4. User service creates profile (idempotent on user_id)
5. Auth activates the account (sets activated_at)
6. Auth publishes user.registered to Redis Streams
7. Auth returns JWT access token + refresh token to client
8. User-worker consumes user.registered (updates any projections)
```

If step 4 rejects the username, step 2 rolls back in the same transaction.
If step 5 crashes after step 4 succeeds, the account is inactive and the user re-registers; the idempotent create returns the same profile.

---

## Failure Modes

| Scenario | What Happens |
|---|---|
| **PostgreSQL down** | Readiness returns 503 (removed from LB). Liveness stays 200 (no restart storm). |
| **Redis down** | Cache: treated as miss (slower, correct). Rate limiting: fails open (requests allowed). Event bus: publish raises DependencyError (502). |
| **Downstream service down** | Circuit breaker opens after 5 failures. Calls fail fast. Half-opens after 10s. |
| **Registration partially completes** | Unactivated account accumulates. Reaper deletes after 1 hour (planned). |
| **Duplicate event delivery** | `claim_event` inserts into `processed_events` in same transaction. PK conflict = already applied = skip. |
| **Poison event** | After 5 delivery attempts, goes to DLQ stream. Metric: `chirp_events_consumed_total{outcome="dead_lettered"}`. |
| **Refresh token theft** | Reuse detection: rotated token presented again = revoke all sessions for the account. |
| **Clock skew** | JWT verification allows 10 seconds of leeway. Beyond that, NTP is the fix. |

---

## Scalability Analysis

### At ~10,000 users
- **Connection pool exhaustion** is the first wall: 10 services x 3 replicas x 15 connections = 450 vs default max_connections of 100. Fix: PgBouncer in transaction mode.
- Cold cache thundering herd after deploy (harmless at this size).
- Single worker per consumer group (fine here).

### At ~100,000 users
- **Timeline fan-out on read** becomes expensive (500-id IN query per timeline load).
- **Celebrity fan-out** (500K followers = 500K feed writes per post).
- **processed_events** grows to millions of rows/day (needs retention job).
- **Hot key contention** on popular account counters (needs sharded counters).
- **PostgreSQL full-text search** stops being viable (swap to OpenSearch).

### At ~1,000,000 users
- Post table needs **partitioning by time** (hundreds of millions of rows).
- Graph table needs **dedicated storage** (billions of rows).
- Feed storage needs **Redis lists per user** (hundreds of millions of entries).
- **Read replicas and read/write splitting** required.
- **Media** must move to S3 + CDN.

---

## Key Architectural Decisions

| Decision | Chosen | Cost |
|---|---|---|
| One PostgreSQL, one DB per service | Separate schemas, no cross-DB queries | Shared max_connections locally |
| HS256 shared secret | Stateless local verification | Any service holding secret could mint tokens (upgrade: RS256) |
| Opaque refresh tokens | SHA-256 stored, rotate on use, reuse = revoke all | One indexed lookup per refresh |
| Redis Streams as broker | Zero new containers | No durable long retention (upgrade: SQS/SNS/Kafka via EventBus interface) |
| At-least-once + idempotent consumers | `processed_events` in same transaction | Table grows forever (needs retention) |
| Publishing not transactional with DB | Commit then publish | Crash between = lost event (upgrade: transactional outbox) |
| Denormalised counters | Event consumer maintains counts | Eventual consistency, drift possible |
| Fail-open rate limiting | Redis down = requests allowed | Security window during Redis outage |
| ULID primary keys | Sortable by time, cross-service friendly | 26 bytes vs 8 (bigint) |
| Cursor pagination everywhere | Keyset on ULID PK | Clients can't jump to page 40 |
| SQLite for unit tests | Fast, no containers needed | Timezone and SQL dialect differences from PostgreSQL |

---

## Roadmap: What's Left to Build

1. **post** -- posts, likes, reposts, bookmarks (the unblocker; 6 services consume its events)
2. **graph** -- follows, blocks, mutes (indexed both directions)
3. **timeline** -- fan-out on read first, hybrid later
4. **media** -- blob storage with S3 backend (presigned uploads)
5. **notification** -- purely event-driven consumer
6. **search** -- PostgreSQL tsvector + GIN (upgradeable to OpenSearch)
7. **messaging** -- conversations, messages, unread counts
8. **moderation** -- reports, admin actions
9. **gateway** -- BFF (CORS, token verification, composition)
10. **Web frontend** -- Vite + React

Plus cross-cutting: transactional outbox, counter reconciliation script, processed_events retention, unactivated-account reaper, end-to-end container tests.

---

## Architecture Diagram

```
                                 ┌─────────────────────────────────────────┐
                                 │              CLIENTS                     │
                                 │   (Browser / Mobile / API consumers)    │
                                 └──────────────────┬──────────────────────┘
                                                    │
                                                    │ HTTPS
                                                    ▼
                                 ┌─────────────────────────────────────────┐
                                 │         API GATEWAY (planned)           │
                                 │   Port 8000 -- BFF, no business logic   │
                                 │   • CORS termination                    │
                                 │   • Token verification (once)           │
                                 │   • Request/correlation ID generation   │
                                 │   • Per-IP rate limiting                │
                                 │   • Screen composition for frontend     │
                                 └──────────────────┬──────────────────────┘
                                                    │
                            ┌───────────────────────┼───────────────────────┐
                            │ HTTP, bearer token forwarded unchanged       │
                            │                                             │
          ┌─────────────────┼─────────────┬─────────────┬─────────────────┐
          │                 │             │             │                 │
          ▼                 ▼             ▼             ▼                 ▼
  ┌──────────────┐  ┌──────────────┐  ┌────────┐  ┌──────────┐  ┌──────────┐
  │  AUTH SVC    │  │  USER SVC    │  │ POST   │  │ TIMELINE │  │ SEARCH   │
  │  Port 8001   │  │  Port 8002   │  │ 8003   │  │  8005    │  │  8006    │
  │              │  │              │  │(planned)│  │(planned) │  │(planned) │
  │ • Register   │  │ • Profiles   │  └───┬────┘  └────┬─────┘  └────┬─────┘
  │ • Login      │  │ • Usernames  │      │            │             │
  │ • Refresh    │  │ • Counters   │      │            │             │
  │ • Logout     │  │ • Search     │      │            │             │
  │ • Sessions   │  │              │      │            │             │
  └──────┬───────┘  └──────┬───────┘      │            │             │
         │                 │              │            │             │
         │  ┌──────────────┘              │            │             │
         │  │  HTTP (sync)                │            │             │
         │  │  during registration        │            │             │
         │  └─────────────────────────────┘            │             │
         │                                             │             │
         │  Every service verifies tokens              │             │
         │  locally with shared secret                 │             │
         │                                             │             │
         └──────────────┬──────────────────────────────┴─────────────┘
                        │
                        │  Publishes events
                        ▼
          ┌─────────────────────────────────────────┐
          │        REDIS STREAMS (Event Bus)        │
          │   One stream per event type             │
          │   One consumer group per service        │
          │   At-least-once delivery                │
          │   Dead letter queue for poison events   │
          └───────────────────┬─────────────────────┘
                              │
                ┌─────────────┼─────────────────────────┐
                │             │                         │
                ▼             ▼                         ▼
     ┌──────────────┐ ┌──────────────┐        ┌──────────────┐
     │ USER-WORKER  │ │ NOTIF-WORKER │  ...   │ SEARCH-WORKER│
     │ (separate    │ │ (planned)    │        │ (planned)    │
     │  process)    │ │              │        │              │
     │              │ │ Consumes:    │        │ Consumes:    │
     │ Consumes:    │ │ post.liked   │        │ post.created │
     │ graph.*      │ │ post.reply   │        │ user.*       │
     │ post.*       │ │ graph.*      │        │              │
     │              │ │              │        │              │
     │ Adjusts:     │ │ Writes:      │        │ Writes:      │
     │ followers_   │ │ notifications│        │ post_search  │
     │ following_   │ │              │        │ hashtag_     │
     │ posts_       │ │              │        │ usage        │
     │ count        │ │              │        │              │
     └──────┬───────┘ └──────────────┘        └──────────────┘
            │
            │ Idempotent claim_event in
            │ same transaction as writes
            │
            ▼
  ┌─────────────────────────────────────────┐
  │         PostgreSQL 16                   │
  │   10 logical databases (1 per service) │
  │                                         │
  │  chirp_auth    chirp_user    chirp_post │
  │  chirp_graph   chirp_timeline          │
  │  chirp_search  chirp_notification      │
  │  chirp_messaging chirp_media           │
  │  chirp_moderation                      │
  │                                         │
  │  ULID PKs, TIMESTAMPTZ, soft delete    │
  │  No cross-service queries              │
  └─────────────────────────────────────────┘
```

### Data Flow Summary

```
                    SYNCHRONOUS                          ASYNCHRONOUS
                    ───────────                          ────────────
  Client ──HTTP──> Gateway ──HTTP──> Service A ──HTTP──> Service B
                                                    │
                                              publish event
                                                    │
                                                    ▼
                                              Redis Streams
                                                    │
                                              ┌─────┴─────┐
                                              ▼           ▼
                                          Worker A    Worker B
                                              │           │
                                              └─────┬─────┘
                                                    │
                                              claim_event
                                              (idempotent)
                                                    │
                                                    ▼
                                              PostgreSQL
```

### Service Dependency Graph

```
              ┌───────┐
              │ AUTH  │──── HTTP ────▶ USER
              └───┬───┘     (register)   │
                  │                      │
                  └──────────┬───────────┘
                             │
                     publish events to
                             │
                             ▼
                     ┌──────────────┐
                     │ REDIS STREAMS│◀──── POST publishes post.*
                     └──────┬───────┘      GRAPH publishes graph.*
                            │
              ┌─────────────┼─────────────────┐
              │             │                 │
              ▼             ▼                 ▼
          USER-WORKER  TIMELINE (reads    SEARCH (indexes
          (counters)   graph + post)      post content)
              │
              ▼
          USER DB (updated counters)
```

---

## Quick Start Commands

```bash
cp .env.example .env        # or: make env (generates JWT secret)
make up                      # build and start everything
make health                  # check readiness of each service
make test                    # run all 44 tests (~3 seconds, SQLite)
make test-integration        # same tests against PostgreSQL
make lint                    # ruff check + format check + mypy
make seed SIZE=small         # 200 users
make seed SIZE=large         # 50,000 users
make logs                    # tail all service logs
```

Interactive API docs: `http://localhost:8001/docs` and `http://localhost:8002/docs`.
