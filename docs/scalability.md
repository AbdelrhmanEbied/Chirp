# Scalability

**Chirp does not currently support 10K, 100K or 1M users.** It has been run
with seed data, not with load. What follows is an analysis of where it would
break and why, intended as a starting hypothesis for your own load testing —
not a claim about measured capacity.

Numbers below are order-of-magnitude reasoning from the query shapes in the
code, not benchmarks.

---

## ~10 000 users

Mostly fine. The failures at this scale are configuration, not architecture.

**Connection pool exhaustion — the first thing you will hit.**
Each service instance opens `DB_POOL_SIZE + DB_MAX_OVERFLOW` = 15 connections.
Ten services × 3 replicas × 15 = 450 connections against a default
`max_connections` of 100. The stack deadlocks long before the database is
actually busy.
*Fix:* PgBouncer in transaction pooling mode, or shrink the pools. Note that
transaction pooling forbids session-level features — this codebase uses none,
which is deliberate.

**Cold cache after deploy.** Every profile read misses and falls to PostgreSQL
at once. Harmless at this size; the same pattern is a thundering herd later.

**Single worker per consumer group.** One `user-worker` process handles every
counter event. Fine here; the ceiling is roughly the throughput of one process.

**Not yet a problem:** timeline assembly, search, media.

---

## ~100 000 users

Architecture starts to matter.

**Timeline fan-out on read.** The current design (once the timeline service
lands) is: fetch the followee list from graph, then ask post for recent posts
by those authors, merge, sort. For a user following 500 accounts that is an
`IN (500 ids)` query per timeline load. At 100K users with a few percent
online, the post service is doing large index scans continuously.
*Fix path:* the hybrid model. Precompute feeds on write for ordinary accounts;
keep read-time merging for the few thousand accounts with huge followee counts,
where fan-out on write would be wasteful. The timeline service is isolated
specifically so this change touches one service.

**Celebrity fan-out.** An account with 500 000 followers produces 500 000 feed
writes per post if you fan out on write. That single event will saturate the
consumer group.
*Fix path:* never fan out above a follower threshold; merge those authors in at
read time.

**`processed_events` growth.** Every consumed event writes a row. At a few
thousand events per second this is millions of rows per day per service.
*Fix:* a retention job deleting rows older than several times the maximum
redelivery window. Not yet implemented.

**Redis Streams memory.** Streams are capped with `MAXLEN ~ 100000` per type.
At this scale a consumer that falls behind loses events silently — the cap
trims from the head.
*Fix:* alert on `chirp_event_queue_depth` well before the cap, and move to a
broker with durable retention.

**Hot key contention.** Counter updates for a popular account serialise on one
row. `UPDATE … SET x = x + 1` is atomic but row-locked.
*Fix:* sharded counters (N rows per user, summed on read) or periodic batched
aggregation.

**Search.** PostgreSQL full-text search over the posts table stops being viable
somewhere around here. The search service exists so it can be replaced by
OpenSearch without touching post or timeline.

---

## ~1 000 000 users

Requires changes this codebase does not have.

**Post table size.** Hundreds of millions of rows. A single PostgreSQL instance
can hold this, but index maintenance, vacuum and backup windows all get
painful.
*Direction:* partition by time first — it is far less invasive than sharding
and matches the access pattern, since feeds read recent posts. Shard by author
id only if partitioning is not enough.

**Graph table size.** The follows table is the biggest thing in the system:
billions of rows, and the access pattern (all followers of X, all followees of
X) needs both directions indexed, which doubles write cost.
*Direction:* dedicated storage. This is the point where people reach for a
graph store or a custom sharded service.

**Feed storage.** Precomputed feeds for a million users, capped at a few
hundred entries each, is hundreds of millions of entries with a high write
rate. Redis lists are the usual answer, with the cap enforced on write and cold
feeds rebuilt on demand rather than stored forever.

**Read replicas and read/write splitting.** Not implemented. The `Database`
class takes one URL; splitting it into writer and reader engines is a
contained change, but every read path then has to declare whether it tolerates
replica lag. That decision has to be made per query, not globally — for
example, the read immediately after a post creation must hit the primary or the
author will not see their own post.

**Media.** Local disk stops being an option entirely. The `MediaStorage`
interface exists for exactly this: presigned S3 uploads and CDN delivery,
without business-logic changes.

---

## What to instrument first

The metrics that will tell you which of the above you have actually hit:

| Metric | What it warns you about |
|---|---|
| `chirp_db_query_duration_seconds` p99 by operation | The query that degrades first |
| `chirp_event_queue_depth` | Consumers falling behind before the stream cap trims |
| `chirp_cache_operations_total{result="miss"}` ratio | Cache sizing and TTL tuning |
| `chirp_http_request_duration_seconds` p99 by route | Which endpoint degrades first |
| `chirp_dependency_requests_total{outcome!="ok"}` | Which synchronous hop is the fragile one |
| PostgreSQL active connections vs `max_connections` | The 10K-scale failure above |

## Deliberate non-optimisations

Things left simple on purpose, so that load testing has something to find:

- fan-out on read, not write
- no read replicas
- no PgBouncer in the Compose file
- no CDN, no image resizing pipeline
- single-process consumers per group
- no query result caching beyond profiles
