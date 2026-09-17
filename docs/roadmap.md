# Roadmap

What is left, in the order it should be built, with the decisions already made
so that building it is execution rather than design.

The ordering is by dependency, not by interest. Every service below depends on
something above it, and building out of order means writing the consumer of an
event before the producer exists.

## Built

- `libs/chirp-common` — configuration, logging, context propagation, error
  hierarchy, HTTP app factory and middleware, service client with retries and a
  circuit breaker, database session management, cursor pagination, cache, rate
  limiting, idempotency, event envelope and bus with Redis Streams and DLQ,
  worker runtime, metrics, JWT.
- `services/auth` — credentials, sessions, rotation, 25 tests.
- `services/user` — profiles, usernames, counters, projector, 19 tests.
- Compose topology, migrations, seed script, tooling, documentation.

---

## 1. post

The unblocker. Six services consume its events and none of them can be
meaningfully built first.

Tables: `posts` (author, text, `reply_to_id`, `quote_of_id`, media ids,
denormalised like/repost/reply counts, `deleted_at`), `likes`, `reposts`,
`bookmarks` — each unique on `(user_id, post_id)`.

Endpoints: create, get, delete, like/unlike, repost/unrepost, bookmark, list a
user's posts, list replies to a post.

Decisions already taken: replies and quotes are columns on `posts`, not
separate tables. Interaction counts update in the same transaction as the
interaction row — same service, same database, so there is no reason to accept
eventual consistency for a number that renders next to the button the user just
pressed. Mentions and hashtags are extracted at write time and published as
events. The unique constraint is what makes double-liking safe; do not check
first and insert second.

Publishes: `post.created`, `post.deleted`, `post.liked`, `post.unliked`,
`post.reposted`, `post.unreposted`, `post.reply_created`, `post.quote_created`,
`post.user_mentioned`, `post.hashtag_used`.

## 2. graph

Tables: `follows`, `blocks`, `mutes`. Index `follows` in **both** directions —
`(follower_id, followee_id)` and `(followee_id, follower_id)` — because the
timeline reads one and the followers list reads the other.

Endpoints: follow, unfollow, followers, following, block, unblock, mute, unmute,
plus an internal batch "is A blocked by any of B[]" used by post, timeline,
notification and messaging.

That internal endpoint is on a hot read path and will be the first thing to
cache. Block relationships change rarely and are read constantly.

Publishes the four `graph.*` events the user service's projector already
consumes — at which point follower counts start moving on their own.

## 3. timeline

Fan-out on read first: ask graph for followees, ask post for recent posts,
merge by id descending, hydrate authors through the user service's batch
endpoint. Chronological. No database of its own initially.

Endpoints: home, user profile timeline, replies timeline.

Build it as its own service anyway — the whole point is that when fan-out on
read stops being viable, the fix (a `feed_entries` table or a Redis list per
user, written by a fan-out worker, with a hybrid path for celebrity accounts)
happens entirely inside this service with its HTTP contract unchanged.
[scalability.md](scalability.md) works through where that cliff is.

## 4. media

Needed before the frontend, because posts and profiles want images.

`MediaStorage` interface: `put`, `delete`, `url_for`. Local-disk backend for
development; the S3 backend implements the same three methods and additionally
issues presigned upload URLs so bytes never traverse the application. Every
other service stores a media **id**, so that swap touches no other table.

Real upload validation belongs here and only here: content-type sniffing from
magic bytes rather than trusting the header, size caps, dimension caps,
rejecting anything that is not actually an image.

## 5. notification

Pure consumer. Subscribes to `post.liked`, `post.reply_created`,
`post.quote_created`, `post.reposted`, `post.user_mentioned`,
`graph.user_followed`; writes a `notifications` row; maintains an unread count.

Endpoints: list (cursor-paginated), unread count, mark read, mark all read.

Every handler needs `claim_event`. A duplicate delivery here means a duplicate
notification, which users notice.

## 6. search

`post_search` with a `tsvector` column and a GIN index, populated from
`post.created`. `hashtag_usage` counts for trending. Everything behind a
`SearchIndex` interface with `index`, `remove` and `query`, so OpenSearch is a
second implementation rather than a rewrite.

Endpoints: search posts, search users, hashtag timeline, trending, explore.

Trending is a windowed count recomputed on a schedule. Not a model.

## 7. messaging

`conversations`, `conversation_participants` (with `last_read_at`), `messages`.
Unread counts computed from `last_read_at` rather than stored, because unlike
follower counts they must be exactly right and the query is cheap when indexed.
Calls graph to refuse delivery between blocked users.

Polling on a cursor is fine to start. WebSockets change the deployment shape
(sticky sessions, connection limits, a pub/sub fan-out layer) and that is a
decision to make deliberately, not by accident.

## 8. moderation

`reports`, `moderation_actions`. Admin endpoints gated on the `admin` scope in
the token. Calls post and user to act on content.

## 9. gateway

Last, because it is a composition layer and there is nothing to compose until
the rest exists.

Verifies the token once, forwards identity, generates request and correlation
ids, terminates CORS for one origin, applies coarse per-IP limits, and composes
the two or three screens whose data genuinely spans services.

It must not accumulate business rules. Every rule that lands here is a rule the
owning service no longer enforces.

## 10. Web frontend

Vite, React, no UI framework. Screens: login/register, home feed, profile, post
composer with images, post detail with replies, search, notifications,
messages, settings. Responsive. Talks only to the gateway.

Deliberately not a showcase. The interesting work in this repository is behind
the API, and a frontend that takes a week is a week not spent on the thing
being demonstrated.

---

## Cross-cutting, worth doing before scale

**Transactional outbox.** The known correctness gap. Right now a service commits
its transaction and then publishes to Redis; if it dies in between, the event is
lost and no retry recovers it. The fix is writing the event to an `outbox` table
in the same transaction and having a relay publish from there. It is
[decisions.md](decisions.md) #6 and it is the first thing to fix if this system
ever carries real data.

**`scripts/reconcile_counters.py`.** Rebuild denormalised counters from source
of truth. Needed as soon as the graph service starts moving them, because
drift is expected rather than exceptional.

**`processed_events` retention.** The table grows forever. A scheduled delete
beyond a window comfortably longer than the DLQ replay horizon.

**Unactivated-account reaper.** Accounts stranded by a failed registration
handshake hold their email address hostage. Delete rows with
`activated_at IS NULL` older than an hour.

**End-to-end container test.** Nothing currently proves two real services
complete the registration handshake over a real network.

---

## Suggested infrastructure sequence

Yours to build; this repository is the input to it. The order that tends to
hurt least:

1. Container registry and CI — build, lint, test, push on every commit.
2. One environment end to end before a second: VPC, EKS, RDS, ElastiCache,
   ALB ingress. Prove one service deploys before deploying ten.
3. **PgBouncer early.** Connection exhaustion is the first wall, and it arrives
   before any query is slow. See [scalability.md](scalability.md).
4. Prometheus and Grafana against the existing `/metrics` endpoints. The
   metrics are already labelled by route template, so the dashboards work
   immediately.
5. Liveness and readiness wired to the existing endpoints — `/health/live` for
   liveness, `/health/ready` for readiness, never the other way round.
6. HPA on request rate and consumer lag. Workers and APIs scale on different
   signals, which is why they are separate deployments.
7. RS256 and a JWKS endpoint, replacing the shared HS256 secret.
8. OpenTelemetry tracing. `correlation_id` already flows through every HTTP hop
   and every event envelope, so the propagation work is done.
9. Load testing, then chaos testing. Both need a deployed environment to mean
   anything, which is why they come last and not first.
