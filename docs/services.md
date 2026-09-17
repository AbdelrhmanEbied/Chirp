# Services

One row per service in the intended system. Two are built; the rest have their
boundary, data and dependencies fixed here so that building them is filling in
a known shape rather than re-litigating the architecture.

A service qualifies as a service in this repository only if it owns data nobody
else writes. Anything that does not own data is a module inside the service
that does.

| Service | Port | Owns | State |
|---|---|---|---|
| auth | 8001 | credentials, sessions | **Built** |
| user | 8002 | profiles, usernames, counters | **Built** |
| post | 8003 | posts, likes, reposts, bookmarks | Planned |
| graph | 8004 | follows, blocks, mutes | Planned |
| timeline | 8005 | feed assembly | Planned |
| search | 8006 | search index, trends | Planned |
| notification | 8007 | notifications, read state | Planned |
| messaging | 8008 | conversations, messages | Planned |
| media | 8009 | upload metadata, storage backend | Planned |
| moderation | 8010 | reports, admin actions | Planned |
| gateway | 8000 | nothing (BFF) | Planned |

---

## auth — built

**Responsibility.** Proving that a request comes from a particular user. That
is all. It does not know what a username is, what a display name is, or whether
the user has posted anything.

**Data.** `accounts` (email, Argon2id password hash, admin flag, activation and
deletion timestamps), `sessions` (one row per logged-in device, holding the
SHA-256 of a refresh token, its expiry, its revocation and what it rotated
into).

**Depends on.** PostgreSQL. Redis for login and registration rate limiting
(degraded to allow-all if Redis is gone — see
[failure-modes.md](failure-modes.md)). The user service over HTTP, during
registration only. Redis Streams to publish `user.registered`.

**Depended on by.** Nothing at runtime. Every other service verifies access
tokens locally with the shared secret and never calls auth to do it. This is
the single most load-bearing design choice in the system: auth is not on the
hot path of any request except login, so it can be the smallest deployment in
the cluster.

**Why it is separate from user.** Credentials have a different blast radius,
different audit requirements and a different rate of change than public
profiles. A schema migration to add a profile field should not touch the table
holding password hashes, and the service that can read password hashes should
have as few endpoints as possible.

**Publishes.** `user.registered`.

**Consumes.** Nothing.

---

## user — built

**Responsibility.** Who a user publicly is, and the cheap aggregate numbers
shown next to that.

**Data.** `user_profiles` (username, display name, bio, location, website,
avatar and banner media ids, denormalised follower/following/post counts),
`username_history` (released handles, so a freed username cannot immediately be
taken by an impersonator).

**Depends on.** PostgreSQL. Redis for the profile cache (invalidated on write;
a cold or dead cache costs latency, not correctness). The event bus, consumed
by a separate worker process.

**Depended on by.** Nearly everything, via `POST /internal/v1/users/summaries`.
Timelines, notifications, search results and conversations all need author
name/avatar/username for a batch of user ids. That endpoint exists specifically
so callers never loop over ids issuing one request each — the N+1 problem
across a service boundary is much worse than inside one, and giving callers a
batch endpoint is the only reliable way to stop them writing the loop.

**Publishes.** `user.profile_updated`, `user.deleted`.

**Consumes.** `graph.user_followed`, `graph.user_unfollowed`, `post.created`,
`post.deleted` — each incrementing or decrementing a counter, each guarded by
`claim_event` so a redelivery does not double-count.

**Counters are not authoritative.** They are a cached aggregate of data owned
by the graph and post services. They can drift under duplicate or lost
delivery; `scripts/reconcile_counters.py` (planned) rebuilds them from source.
A wrong follower count is a cosmetic bug. A wrong follow edge would be a
correctness bug, which is why the edge lives in the graph service and only the
number lives here.

---

## post — planned

**Responsibility.** Post content and the interactions attached to a post.

**Data.** `posts` (author id, text, reply-to id, quote-of id, media ids,
soft-delete), `likes` (unique on `(user_id, post_id)`), `reposts` (same),
`bookmarks` (same). Reply and quote are columns on `posts`, not separate
tables: they are posts with a parent, and splitting them would triple the work
of every timeline read.

**Depends on.** PostgreSQL, the event bus, the user service for author
hydration, the media service to validate that referenced media ids exist and
belong to the author.

**Key decisions already made.** Like and repost counts are denormalised onto
`posts` and updated in the same transaction as the like row — same database,
same service, so a transaction is available and there is no reason to accept
eventual consistency for a number rendered next to the button the user just
pressed. Mentions and hashtags are extracted at write time and published as
events, not parsed at read time.

**Publishes.** `post.created`, `post.deleted`, `post.liked`, `post.unliked`,
`post.reposted`, `post.unreposted`, `post.reply_created`, `post.quote_created`,
`post.user_mentioned`, `post.hashtag_used`.

---

## graph — planned

**Responsibility.** The directed edges between users: follows, blocks, mutes.

**Data.** `follows` (`follower_id`, `followee_id`, unique, indexed both
directions), `blocks`, `mutes`.

**Why both directions are indexed.** "Who do I follow" drives the timeline;
"who follows me" drives the followers list and, later, fan-out on write. One
composite index serves one of those and not the other.

**Blocks are enforced here and applied everywhere.** The graph service answers
"is A blocked by B" for the post, timeline, notification and messaging
services. This is a synchronous call on read paths, which makes it a caching
target early: block relationships change rarely and are read constantly.

**Publishes.** `graph.user_followed`, `graph.user_unfollowed`,
`graph.user_blocked`, `graph.user_unblocked`.

---

## timeline — planned

**Responsibility.** Assembling feeds. It owns no posts and no follows.

**Data.** Initially none — the first implementation is fan-out on read: ask
graph for followees, ask post for their recent posts, merge by id descending.
This is the honest starting point and it is fine at seed-data scale.

The service exists as its own deployment precisely because that will stop being
fine. When it does, the fix is a `feed_entries` table or a Redis list per user
populated by a fan-out worker, plus a hybrid path for users with very large
follower counts — and that change happens entirely inside this service, with
its HTTP contract unchanged. [scalability.md](scalability.md) works through
where the cliff is.

**Depends on.** graph, post, user. No database at first.

---

## search — planned

**Responsibility.** Finding users, posts and hashtags; computing trends.

**Data.** A `post_search` table with a PostgreSQL `tsvector` column and a GIN
index, populated from `post.created` events, plus `hashtag_usage` counts for
trending.

**The abstraction that matters.** All querying goes through a `SearchIndex`
interface with `index()`, `remove()` and `query()`. PostgreSQL full-text search
is the local implementation; OpenSearch is a second implementation of the same
three methods. Nothing outside this service knows which is in use. No
embeddings, no vector search.

**Trending** is a windowed count of `post.hashtag_used` events, recomputed on a
schedule, not a ranking model.

---

## notification — planned

**Responsibility.** Turning events into a user's notification list.

**Data.** `notifications` (recipient, type, actor, subject id, read state) and a
per-user unread count.

**This service is purely a consumer.** It has no synchronous callers except the
read endpoints. Every notification originates from an event another service
published — like, reply, follow, repost, mention, quote. That is what makes
asynchrony correct here rather than fashionable: the user who pressed "like"
does not need their request to block while someone else's notification row is
written, and a notification arriving 200ms late is not a defect.

**Consumes.** `post.liked`, `post.reply_created`, `post.quote_created`,
`post.reposted`, `post.user_mentioned`, `graph.user_followed`.

---

## messaging — planned

**Responsibility.** Direct messages.

**Data.** `conversations`, `conversation_participants` (with `last_read_at`),
`messages`.

**Unread counts** are computed from `last_read_at` rather than stored as a
counter, because unlike follower counts they must be exactly right and the
query is cheap when indexed on `(conversation_id, id)`.

**Depends on.** graph, to refuse delivery between blocked users.

**Publishes.** `messaging.message_sent`.

---

## media — planned

**Responsibility.** Where bytes live, and the metadata about them.

**Data.** `media` (owner, content type, size, dimensions, storage key, state).

**No bytes in PostgreSQL.** A `MediaStorage` interface with `put`, `delete` and
`url_for` is implemented by a local-disk backend for development and an S3
backend for deployment. The S3 version also issues presigned upload URLs so
that bytes never traverse the application at all; `url_for` becomes a CloudFront
URL. Because every other service stores a media *id* rather than a URL, that
migration touches no other table.

**Upload validation** — content type sniffing, size limits, dimension limits,
rejecting anything that is not a real image — belongs here and nowhere else.

**Publishes.** `media.uploaded`, `media.deleted`.

---

## moderation — planned

**Responsibility.** Reports and administrative action.

**Data.** `reports` (reporter, target type, target id, reason, state),
`moderation_actions` (admin, action, target, reason).

**Depends on.** post and user, to act on content. Admin-only authorisation via
the `is_admin` claim minted by auth.

**Publishes.** `moderation.report_created`, `moderation.content_actioned`.

---

## gateway — planned

**Responsibility.** One origin for the browser. It owns no data and contains no
domain logic; if a rule is about *what* is allowed, it belongs in the service
that owns the data, not here.

**What it legitimately does.** Terminates CORS for a single origin, verifies the
access token once and forwards identity, applies coarse per-IP rate limits,
generates the request and correlation ids that flow through every downstream
call, and composes the handful of screens whose data spans services — a
timeline page needs posts, authors, like state and follow state, and making the
browser issue four round trips over a mobile connection to assemble one screen
is the problem a BFF exists to solve.

**What it must not become.** A place where business rules accumulate because it
is convenient. Every rule added here is a rule that the owning service no
longer enforces, which means the rule disappears the moment anything talks to
that service directly.

---

## Workers

Workers are deployed separately from their service's API even though they share
a codebase — `user-worker` in `docker-compose.yml` is the pattern. The reason is
operational: consumer lag and request latency are different problems with
different scaling triggers, and a worker stuck retrying a poison event must not
be able to take request-serving capacity down with it. They share code because
they share the same domain logic and models, and duplicating those to achieve
process separation would be a worse trade.
