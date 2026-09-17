# Database

## Ownership

Each service owns its tables outright. No service reads or writes another
service's tables — not for a quick join, not for a report, not for a migration
script. The only way to get at another service's data is its API or its events.

This is the rule that makes the rest of the architecture real. A shared
database with per-service schemas would be simpler to operate and would let you
JOIN across boundaries, and the moment anyone did, the services would be one
deployable system wearing ten containers: you could not migrate a table without
coordinating every consumer, and you could not scale, cache or fail one service
independently of the others.

**The visible cost**, paid constantly: there are no cross-service foreign keys
and no cross-service transactions. A profile row references `account.id` with
no constraint enforcing it. Registration is a two-step handshake rather than
one `INSERT ... COMMIT`. Timelines hydrate authors with a batch HTTP call
rather than a join. Every one of those is a real loss, accepted deliberately.

## Local topology

One PostgreSQL 16 container, ten logical databases:

```
chirp_auth  chirp_user  chirp_post  chirp_graph  chirp_timeline
chirp_search  chirp_notification  chirp_messaging  chirp_media  chirp_moderation
```

Created by `docker/postgres/10-create-databases.sh` on first start. Ten
PostgreSQL containers on a 16 GB development machine would spend roughly a
gigabyte of RAM to demonstrate a point the code already enforces — separate
connection strings, no cross-database queries. In deployment each `DATABASE_URL`
points at its own RDS instance and nothing in the application changes.

The honest caveat: a single server means shared `max_connections`, shared CPU
and a shared blast radius locally. `docker-compose.yml` is where you would
split them if you wanted to feel the real thing.

## Conventions

**ULID primary keys**, 26-character Crockford base32 strings. Lexicographically
sortable by creation time, which is what makes keyset pagination on `id` work
without a separate timestamp index, and what lets a service generate an id
before insert (needed to build an event envelope inside the same transaction).
The cost over a `bigint` is 26 bytes instead of 8, in every index and every
foreign key — worth it here, and worth knowing about.

**Timestamps.** `created_at` and `updated_at` on everything via `TimestampMixin`,
always `TIMESTAMPTZ`, always UTC.

**Soft deletion** via `SoftDeleteMixin`'s nullable `deleted_at` where content
must survive its own deletion — a deleted post still has to keep replies
coherent, a deleted account must keep its username parked. Every query against
a soft-deletable table filters `deleted_at IS NULL`; forgetting that filter is
the characteristic bug of this pattern, which is why the composite indexes
below include `deleted_at`.

**Naming.** Tables plural and snake_case, indexes `ix_<table>_<columns>`,
constraints `ck_<table>_<rule>`.

## Schema — auth

**`accounts`** — one per user. `id` is the user id everywhere in the system.

| Column | Type | Notes |
|---|---|---|
| `id` | `varchar(26)` | PK, ULID |
| `email` | `varchar(320)` | **unique**, indexed |
| `password_hash` | `varchar(255)` | Argon2id |
| `is_admin` | `boolean` | Minted into the token as a scope |
| `activated_at` | `timestamptz` | Null until the profile handshake succeeds |
| `last_login_at` | `timestamptz` | |
| `deleted_at` | `timestamptz` | Soft delete |

`activated_at` is the interesting column. A row with it null is an account
whose profile creation did not complete, and it cannot log in. That is how the
system survives the user service being down mid-registration without needing a
distributed transaction.

**`sessions`** — one per logged-in device.

| Column | Type | Notes |
|---|---|---|
| `id` | `varchar(26)` | PK. Appears in tokens as `sid` |
| `account_id` | `varchar(26)` | FK → `accounts.id`, indexed |
| `token_hash` | `varchar(64)` | **unique**. SHA-256 of the refresh token |
| `expires_at` | `timestamptz` | |
| `revoked_at` | `timestamptz` | |
| `rotated_to_id` | `varchar(26)` | The session that replaced this one |
| `user_agent`, `ip_address` | | Shown in the sessions list |

Indexes: `ix_sessions_account_active (account_id, revoked_at)` for "list my
sessions" and bulk revocation; `ix_sessions_expires_at` for the cleanup job.

The refresh token itself is never stored — only its SHA-256. A database dump
therefore does not hand an attacker a set of working sessions. `rotated_to_id`
is what makes theft detectable: a token that has already been exchanged should
never be presented again, so when one is, the whole chain is revoked.

This is the one place in the system with a real foreign key, because both
tables are owned by the same service.

## Schema — user

**`user_profiles`** — `id` matches `accounts.id`, with no constraint expressing
that.

| Column | Type | Notes |
|---|---|---|
| `id` | `varchar(26)` | PK. Same value as the account id |
| `username` | `varchar(20)` | **unique**, indexed, stored lowercase |
| `display_name` | `varchar(50)` | Indexed for search |
| `bio` | `text` | |
| `location`, `website` | | |
| `avatar_media_id`, `banner_media_id` | `varchar(26)` | Media **ids**, not URLs |
| `username_changed_at` | `timestamptz` | Drives the 30-day cooldown |
| `followers_count`, `following_count`, `posts_count` | `bigint` | `CHECK >= 0` |
| `deleted_at` | `timestamptz` | |

Storing media ids rather than URLs means moving from local disk to S3 and
CloudFront changes the media service and nothing else. Storing a URL would put
a hostname in a million user rows.

The `CHECK (followers_count >= 0)` constraints exist because a duplicate
decrement is the realistic failure mode of event-driven counters, and a
negative follower count rendered in a UI is worse than a failed update. The
projector clamps at zero with a CASE expression rather than `GREATEST`, which
is not portable to SQLite and therefore not testable.

**`username_history`** — released handles.

| Column | Type | Notes |
|---|---|---|
| `id` | `varchar(26)` | PK, ULID |
| `user_id` | `varchar(26)` | Indexed |
| `username` | `varchar(20)` | Indexed — checked when claiming a handle |
| `released_at` | `timestamptz` | |

Without this table, changing your username frees it instantly and anyone can
take it and inherit your mentions. With it, the handle is parked.

## Shared: `processed_events`

Present in every service that consumes events, defined once in
`chirp_common.idempotency`.

| Column | Type | Notes |
|---|---|---|
| `event_id` | `varchar(26)` | PK |
| `consumer` | `varchar(100)` | PK — same event, different consumers |
| `processed_at` | `timestamptz` | |

The bus is at-least-once, so every consumer must assume redelivery. `claim_event`
does an `INSERT ... ON CONFLICT DO NOTHING RETURNING` — one round trip, atomic,
no read-then-write race — and returns whether this consumer has seen this event
before. The composite key on `(event_id, consumer)` is what allows two consumers
in the same service to process the same event independently.

This table grows monotonically and needs a retention job (delete beyond a window
comfortably longer than the DLQ replay horizon). Noted in
[scalability.md](scalability.md); not yet written.

## Migrations

Alembic, one history per service, run as a one-shot container before the
service starts:

```yaml
auth-migrate:
  command: alembic upgrade head
auth:
  depends_on:
    auth-migrate: { condition: service_completed_successfully }
```

Migrations never run inside the application process. If three replicas start
simultaneously and each tries to migrate, you get lock contention at best and
a half-applied schema at worst. A one-shot job is a Kubernetes Job or an ECS
task in deployment — the same shape.

```bash
make migrate                                    # everything, to head
cd services/auth && alembic revision -m "..."   # new revision
cd services/auth && alembic downgrade -1        # back one
```

Alembic needs a synchronous driver, so `chirp_common.db.migrations` rewrites
`postgresql+asyncpg://` to `postgresql+psycopg://` before handing over the URL.
One `DATABASE_URL` per service, two drivers, no duplicated configuration.

**Autogenerate is a draft, not an answer.** It misses index renames, cannot see
data migrations, and will happily generate a `DROP` for a table it does not know
about. Read every generated revision.

## Connection pooling

`DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=5` per service instance — a ceiling of 15
connections each. Ten services at three replicas is 450 connections against a
default `max_connections` of 100.

That is the arithmetic that breaks first as this system grows, before any query
is slow and before any table is large. PgBouncer in transaction mode is the
answer and it is infrastructure, which puts it on your side of the line. See
[scalability.md](scalability.md).

`DB_STATEMENT_TIMEOUT_MS=5000` is set per connection. A query that has run for
five seconds in a request-serving path is not going to finish usefully, and
letting it continue holds a connection the pool needs.

## Query discipline

**No N+1, anywhere.** Inside a service that means explicit eager loading. Across
services it means batch endpoints: `POST /internal/v1/users/summaries` takes a
list of ids specifically so that no caller ever writes a loop of HTTP requests.
An N+1 over a network with 3-second timeouts is not a performance problem, it is
an outage.

**Indexes exist for named queries.** Every index in the migrations corresponds
to a query in a repository. An index that nothing uses is write amplification on
every insert.

**Transactions are per request**, held by the session dependency, committed by
the route. They are as short as possible: no HTTP call is ever made with a
transaction open, because a 3-second downstream timeout would otherwise mean a
3-second row lock. The registration handshake is structured around this — commit
the account, call the user service, then a second transaction to activate.
