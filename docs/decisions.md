# Decisions

The choices that are arguable, what was chosen, and what it costs.

---

### One PostgreSQL server, one database per service

**Chosen:** a single `postgres:16` container hosting `chirp_auth`,
`chirp_user`, `chirp_post`, … Each service has its own database, its own
connection string, its own migration history, and no cross-database queries or
foreign keys.

**Alternative:** one container per service.

**Why:** ten PostgreSQL containers plus Redis plus ten application containers
does not comfortably fit on a development laptop, and the thing that actually
matters — that no service can read another's tables — is enforced by separate
databases and separate engines just as well as by separate servers. Moving each
database to its own RDS instance changes one environment variable per service
and nothing else.

**Cost:** a shared `max_connections` budget locally, and no ability to
demonstrate per-service failover on a laptop. Both are deployment concerns.

---

### Shared HS256 secret for access tokens

**Chosen:** the auth service mints tokens; every service verifies them locally
with the same secret.

**Alternative:** RS256 with a JWKS endpoint, or a token introspection call to
auth on every request.

**Why:** introspection puts auth in the hot path of every request in the
system, which makes it the thing that takes the whole site down. Local
verification is a signature check with no I/O.

**Cost:** any service holding the secret could mint tokens. This is a real
weakness. The upgrade is RS256 — auth holds the private key, publishes a JWKS
endpoint, services cache public keys — and it is confined to
`chirp_common/auth/jwt.py`.

---

### Opaque refresh tokens, not JWTs

**Chosen:** refresh tokens are 32 random bytes; only their SHA-256 is stored.
Every refresh rotates the token, and presenting an already-rotated token
revokes every session for that account.

**Why:** a refresh token must be revocable the moment a user logs out. A
self-contained signed token can only be revoked via a server-side lookup, at
which point it may as well be an opaque id. Rotation plus reuse detection turns
a stolen token into a detectable event rather than a silent long-lived
compromise.

**Cost:** one indexed lookup per refresh, and a legitimate client that loses a
response mid-rotation gets logged out. That is the correct trade against theft.

---

### Redis Streams as the local broker

**Chosen:** Redis Streams, behind the `EventBus` interface.

**Alternatives:** RabbitMQ (one more container, richer routing), Kafka
(genuinely heavy for a laptop), PostgreSQL `LISTEN/NOTIFY` (no consumer groups,
no redelivery).

**Why:** Redis is already required for caching, counters and rate limiting, so
this adds zero containers. Streams provide the primitives that make consumers
realistic: consumer groups, per-consumer pending lists, redelivery of
unacknowledged entries, and a stable entry id.

**Cost:** no durable long retention, no partitioned ordering, no broker-side
dead-letter policy — Chirp implements its own DLQ stream. Swapping in SNS/SQS
or Kafka means one new class implementing `EventBus`.

---

### At-least-once delivery, idempotent consumers

**Chosen:** events may be delivered more than once. Consumers deduplicate via a
`processed_events` table written **in the same transaction** as their effects.

**Why:** exactly-once across a broker and a database requires distributed
transactions. At-least-once plus idempotency is the standard, workable answer,
and the transactional claim makes "did the work" and "recorded the work" atomic
rather than racy.

**Cost:** one extra row and one extra index per consumed event. The table needs
periodic pruning; that is noted in [failure-modes.md](failure-modes.md).

---

### Publishing is not transactional with the database write

**Chosen:** a handler commits its database transaction, then publishes.

**Why not an outbox:** the transactional outbox pattern (write the event to an
`outbox` table in the same transaction, relay it separately) is the correct
answer and is the documented upgrade path. It is not implemented yet because it
adds a relay process per service, and the current consumers — counters, feeds,
notifications — degrade acceptably if an event is lost.

**Cost:** a crash between commit and publish loses the event. A follower count
drifts; `scripts/reconcile_counters.py` (planned) rebuilds it. **Do not** add a
consumer whose correctness depends on never missing an event until the outbox
exists.

---

### Denormalised counters

**Chosen:** `followers_count` and friends live on `user_profiles`, maintained
by an event consumer.

**Why:** `SELECT COUNT(*) FROM follows WHERE followee_id = ?` on an account
with a million followers is an index scan on every profile view, and profiles
are viewed far more than follows are created.

**Cost:** eventual consistency. The number can lag by the queue depth and can
drift if an event is lost. Acceptable for a follower count; it would not be
acceptable for the follow edge itself, which is why that stays a real row.

---

### Fail-open rate limiting

**Chosen:** if Redis is unreachable, requests are allowed.

**Why:** failing closed turns a cache outage into a total outage.

**Cost:** a Redis outage is also a rate-limit outage. For a login endpoint that
is a genuine security window. An edge-level limit (ALB/WAF/ingress) is the
correct second layer and belongs in the deployment you build.

---

### ULID primary keys

**Chosen:** 26-character Crockford base32 ULIDs generated by the owning service.

**Why:** ids cross service boundaries inside events, so they cannot come from a
shared sequence. Unlike UUIDv4 they sort by creation time, which makes cursor
pagination a plain index range scan and keeps btree inserts near-append-only
instead of scattering writes across the index.

**Cost:** 26 bytes instead of 8, and the creation timestamp is inferable from
the id. Neither matters here.

---

### Cursor pagination everywhere it matters

**Chosen:** keyset pagination on the ULID primary key; offset only for small
bounded lists.

**Why:** `OFFSET 50000` makes PostgreSQL walk and discard 50 000 rows, and
offset paging skips or duplicates rows when new items arrive mid-scroll —
exactly what a live feed does.

**Cost:** clients cannot jump to page 40. Feeds do not need that.

---

### SQLite for the unit suites

**Chosen:** tests run on SQLite by default; `TEST_DATABASE_URL` points them at
PostgreSQL.

**Why:** `make test` needing no containers is worth a lot for iteration speed.

**Cost:** real. SQLite returns naive datetimes where PostgreSQL returns aware
ones (which is why `chirp_common.timeutil.ensure_utc` exists), and it does not
support `ON CONFLICT … RETURNING` the same way (which is why
`idempotency.claim_event` branches on dialect). Anything touching
PostgreSQL-specific SQL must be run against PostgreSQL before it is trusted.
