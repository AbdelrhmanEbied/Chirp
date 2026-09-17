# Architecture

## The shape

```
                     ┌──────────────┐
  browser  ────────▶ │ API gateway  │  (planned)
                     └──────┬───────┘
                            │ HTTP, bearer token forwarded unchanged
        ┌───────────────┬───┴────┬────────────────┬──────────────┐
        ▼               ▼        ▼                ▼              ▼
    ┌───────┐      ┌────────┐ ┌──────┐      ┌──────────┐   ┌──────────┐
    │ auth  │◀────▶│  user  │ │ post │      │ timeline │   │  search  │
    └───┬───┘      └───┬────┘ └──┬───┘      └────┬─────┘   └────┬─────┘
        │              │         │               │              │
   chirp_auth     chirp_user  chirp_post    chirp_timeline  chirp_search
        │              │         │               │              │
        └──────────────┴────┬────┴───────────────┴──────────────┘
                            ▼
                  Redis Streams (event bus)
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
          user-worker          notification-worker   (consumers)
```

Solid arrows are synchronous HTTP. The bus at the bottom is asynchronous. A
service never reads another service's database.

## Why these boundaries

The services are split along **ownership of a noun and its invariants**, not
along "one table per service". A boundary is worth having when the thing on
either side has a different consistency requirement, a different read/write
ratio, or a different scaling signal.

| Service | Owns | Why it is separate |
|---|---|---|
| auth | credentials, sessions | Different security posture from everything else: it is the only service holding password hashes, the only one that mints tokens, and the one you would isolate first. Its traffic is tiny compared to reads. |
| user | profiles, usernames, counters | Read enormously more than written, cacheable, and the hydration source for every other service's responses. |
| post | posts, replies, likes, reposts, bookmarks | The write-heavy core. Sharding pressure lands here first. |
| graph | follows, blocks, mutes | Small rows, huge count, and the access pattern (all followers of X) is unlike anything else. |
| timeline | feed assembly and feed cache | The one component whose architecture you will want to change repeatedly — read fan-out, write fan-out, hybrid. Isolating it means those experiments touch one service. |
| search | indexes | Replaceable wholesale by OpenSearch without touching the rest. |
| notification | notifications, read state | Purely event-driven; a backlog here must never slow a post. |
| messaging | conversations, messages | Different privacy model: nothing here is public. |
| media | blobs, metadata | The only service that touches large binaries, and the only one whose storage backend changes (disk → S3 → CDN). |
| moderation | reports, actions | Different audience (staff), different authorisation model. |

What is deliberately **not** split: likes do not get their own service even
though they are high volume, because a like is meaningless without its post and
the two are written together. That would be a boundary for the sake of a count.

## What every service has

Because they all come from `chirp_common.http.create_app`, every service has
identical operational behaviour:

- `GET /health/live` — process is up; **never** touches a dependency, so a
  database blip cannot trigger a restart storm
- `GET /health/ready` — dependencies reachable; critical failures return 503
  so the load balancer removes the instance without killing it
- `GET /metrics` — Prometheus text format; the app runs fine with nothing scraping it
- `GET /docs`, `GET /openapi.json` — generated from the route signatures
- structured JSON logs with `request_id` and `correlation_id` on every line
- the same error envelope, the same validation behaviour, the same CORS and
  body-size handling
- configuration exclusively from environment variables

## Request path

1. The gateway generates a `correlation_id` (or accepts one) and forwards the
   bearer token unchanged.
2. Each service verifies the token **locally** with the shared secret. There is
   no auth round-trip per request; see [decisions.md](decisions.md) for the
   tradeoff and the RS256/JWKS upgrade path.
3. `RequestContextMiddleware` binds ids into a `ContextVar`, so logs, outbound
   HTTP headers and published events all carry them without being threaded
   through every function signature.
4. Handlers hold no logic. `routes.py` validates and delegates to `service.py`,
   which holds no SQL and delegates to `repository.py`.

## Synchronous or asynchronous

Synchronous when the caller cannot proceed without the answer, or when a
failure must be visible to the user:

- registration → profile creation (a username clash must return 409 *now*)
- timeline assembly → author hydration (an unrendered post is not useful)

Asynchronous when the side effect is allowed to be slightly late:

- counters, notifications, search indexing, timeline fan-out

The failure mode of getting this wrong in each direction: synchronous-everywhere
turns one slow service into a site-wide outage; asynchronous-everywhere makes
"create a post and see it appear" a race.
