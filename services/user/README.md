# user service

Who a user publicly is, and the cheap aggregate numbers shown next to that.

Nearly every other service depends on this one, because a timeline, a
notification list, a set of search results and a conversation all need the same
thing: name, username and avatar for a batch of user ids.

Port 8002. Database `chirp_user`. Runs a second process, `user-worker`, for
event consumption.

---

## What it owns

**`user_profiles`** — username (lowercase, unique), display name, bio,
location, website, avatar and banner media **ids**, `username_changed_at`, and
denormalised `followers_count` / `following_count` / `posts_count` with
`CHECK >= 0`. `id` is the same value as the auth service's account id, with no
foreign key expressing that — the row lives in another database owned by
another service.

**`username_history`** — handles released by a username change, so a freed
handle cannot immediately be claimed by an impersonator.

Media **ids** rather than URLs: moving from local disk to S3 and CloudFront
changes the media service and nothing else. Storing a URL would bake a hostname
into every user row.

## Endpoints

| Method | Path | Auth | |
|---|---|---|---|
| GET | `/api/v1/users/me` | Bearer | |
| PATCH | `/api/v1/users/me` | Bearer | Display name, bio, location, website |
| PUT | `/api/v1/users/me/username` | Bearer | 30-day cooldown; old handle parked |
| PUT | `/api/v1/users/me/media` | Bearer | Avatar and banner |
| DELETE | `/api/v1/users/me` | Bearer | 204. Soft delete |
| GET | `/api/v1/users/search` | — | Username prefix search |
| GET | `/api/v1/users/{username}` | — | Public profile |
| POST | `/internal/v1/users` | internal | Idempotent. Called by auth during registration |
| POST | `/internal/v1/users/summaries` | internal | Batch hydration |

`/internal/v1/*` is excluded from the OpenAPI schema and is not routed through
the gateway. Deployed, it should also be restricted at the network layer rather
than relying on routing alone.

## The three decisions worth knowing

### The batch endpoint exists to prevent an N+1 across the network

`POST /internal/v1/users/summaries` takes a list of ids and returns a list of
summaries. Every caller that renders a list of things authored by people uses
it.

Without it, the obvious implementation of a timeline is a loop issuing one HTTP
request per post author. Twenty posts becomes twenty requests, each with a
3-second timeout, each with connection setup. An N+1 inside one database is a
performance problem; an N+1 across a service boundary is an outage waiting for
traffic. The only reliable way to stop callers writing that loop is to give them
a batch endpoint that is easier to use than the loop.

### Counters are a projection, not the truth

`followers_count` is a cached aggregate of data owned by the graph service.
`posts_count` belongs to the post service. They are maintained by
`CounterProjector` in the worker process, consuming `graph.user_followed`,
`graph.user_unfollowed`, `post.created` and `post.deleted`.

Every handler is guarded by `claim_event`, so a redelivery does not
double-count. Decrements clamp at zero — with a `CASE` rather than `GREATEST`,
which is not portable to SQLite and therefore not testable. The `CHECK >= 0`
constraint is the backstop.

Drift is possible and acceptable. A wrong follower count is cosmetic; a wrong
follow *edge* would be a correctness bug, which is exactly why the edge lives in
the graph service and only the number lives here.
`scripts/reconcile_counters.py` (see
[../../docs/roadmap.md](../../docs/roadmap.md)) rebuilds them from source.

### Username changes park the old handle

Changing a username without keeping the old one free-for-all means anyone can
take the handle you just released and inherit your mentions. So the old handle
goes into `username_history` and is checked when anyone tries to claim it.
There is also a 30-day cooldown between changes, and a reserved list that keeps
`admin` and friends unregisterable.

## Caching

Profiles are cached in Redis with a short TTL and invalidated on write. The
cache is not load-bearing: `CACHE_ENABLED=false` makes every read hit
PostgreSQL and every test passes. If Redis dies, profile reads get slower and
stay correct.

That is the rule everywhere in this repository — Redis is never the sole source
of truth for anything.

## Events

**Publishes** `user.profile_updated`, `user.deleted`.

**Consumes** `graph.user_followed`, `graph.user_unfollowed`, `post.created`,
`post.deleted`.

The worker is a separate container even though it shares this codebase.
Consumer lag and request latency are different problems with different scaling
triggers, and a worker stuck retrying a poison event must not be able to take
request-serving capacity down with it.

```bash
python -m app.worker
```

Note that the graph and post services do not exist yet, so nothing currently
publishes the events the projector consumes. The projector is tested against
synthesised envelopes; it starts doing real work the day the graph service
ships.

## Configuration

| Variable | Default | |
|---|---|---|
| `PROFILE_CACHE_TTL_SECONDS` | 60 | |
| `USERNAME_CHANGE_COOLDOWN_DAYS` | 30 | |
| `MAX_PROFILE_BATCH` | 100 | Cap on the summaries endpoint |

## Layout

```
app/
  main.py          create_app + lifespan + health checks
  settings.py      environment-derived configuration
  dependencies.py  composition root
  routes.py        public + internal routers
  service.py       domain logic
  repository.py    SQL only
  models.py        user_profiles, username_history
  schemas.py       request/response contracts
  worker.py        CounterProjector — separate process
migrations/
tests/             19 tests
```

## Tests

```bash
cd services/user && python3 -m pytest -q          # 19 passed
```

Worth reading: `test_counter_projection.py` for duplicate delivery and the
negative clamp, `test_username_changes.py` for the cooldown and the
impersonation path.

## Running standalone

```bash
docker compose up -d postgres redis
cd services/user
export DATABASE_URL="postgresql+asyncpg://chirp:chirp-local-password@localhost:5432/chirp_user"
export REDIS_URL="redis://localhost:6379/0"
export EVENT_BUS_URL="redis://localhost:6379/1"
export JWT_SECRET="<the value from .env>"
alembic upgrade head
uvicorn app.main:app --reload --port 8002
```
