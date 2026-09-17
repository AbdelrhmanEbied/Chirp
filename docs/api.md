# API conventions

Every service exposes the same shapes for the same things. The point is that a
client that can talk to one service already knows how to talk to the next one:
same error envelope, same pagination, same auth header, same health endpoints.

Interactive OpenAPI is generated per service at `/docs`, with the raw document
at `/openapi.json`. This document covers the conventions those schemas assume.

---

## Versioning

Public routes are prefixed `/api/v1/<resource>`. Internal routes — called only
by sibling services, never routed publicly by the gateway — are prefixed
`/internal/v1/` and are excluded from the OpenAPI schema.

The prefix is in the path rather than in a header because it has to survive
being read in a log line and pasted into `curl`. `v2` would be a parallel
router in the same service, not a new deployment.

Backwards-compatible changes (new optional fields, new endpoints) happen within
`v1`. Removing a field or changing its meaning does not.

---

## Authentication

```
Authorization: Bearer <access_token>
```

Access tokens are JWTs, HS256, minted only by the auth service and **verified
locally by every service** — no network call, no shared session store, no
introspection endpoint. Claims:

| Claim | Meaning |
|---|---|
| `sub` | user id (ULID) — the same id in every service |
| `sid` | session id, so a single device can be revoked |
| `jti` | token id |
| `iss` / `aud` | `chirp.auth` / `chirp.api`, both verified |
| `exp` / `iat` | 15 minute default lifetime |
| `scopes` | includes `admin` for administrative accounts |

The consequence worth understanding: **an access token cannot be revoked before
it expires.** Logging out revokes the refresh token, so no new access token can
be minted, but the one already issued stays valid for up to fifteen minutes.
That is the price of stateless verification and it is why the access TTL is
short. A revocation list in Redis checked by every service would close the gap
and reintroduce the shared dependency the design is avoiding.

Refresh tokens are **not** JWTs. They are opaque random strings; only their
SHA-256 is stored. They rotate on every use, and presenting an already-rotated
token revokes every session for that account, because the only way that happens
is theft.

`HS256` with a shared secret means every service can mint tokens, not just
verify them. That is acceptable for a local topology and not for a real one;
the upgrade is RS256 with auth holding the private key and everyone else
fetching a public JWKS. `JWTCodec` takes the algorithm as configuration
precisely so that change stays small. See [decisions.md](decisions.md).

---

## Errors

Every error — validation failures, domain errors, unhandled exceptions — comes
back in one envelope:

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

`code` is the stable, machine-readable part. `message` is for humans and may be
reworded. `details` is present only when there is something structured to say.
`request_id` matches the `x-request-id` response header and the `request_id` in
every log line produced by that request, which is how a user-reported error
becomes a log query.

| HTTP | `code` | Raised when |
|---|---|---|
| 400 | `bad_request` | Malformed input that is not a field validation failure |
| 400 | `invalid_cursor` | A pagination cursor is corrupt or from an older version |
| 401 | `unauthorized` | Missing, malformed, expired or badly signed token |
| 403 | `forbidden` | Authenticated, but not allowed to touch this resource |
| 404 | `not_found` | Resource does not exist, or is soft-deleted, or is not yours to see |
| 409 | `conflict` | Unique constraint: email or username taken, already following |
| 422 | `validation_error` | Field-level failure; `details.fields` lists them |
| 429 | `rate_limited` | Over the limit; `Retry-After` header is set |
| 502 | `dependency_error` | A downstream service failed or timed out |
| 503 | `service_unavailable` | This service cannot serve requests right now |
| 500 | `internal_error` | Unhandled. Message is always generic |

Two rules that matter for security. **404 rather than 403** when revealing
existence is itself a leak. And a 500 never carries the real exception message
— that goes to the logs with the request id attached, never to the client.

---

## Pagination

Feeds, replies, followers, search results and messages are cursor-paginated:

```
GET /api/v1/timeline/home?limit=20&cursor=djE6MDFKOFpDNUsz...
```

```json
{
  "data": [ ... ],
  "page": {
    "next_cursor": "djE6MDFKOFpDNUsz...",
    "has_more": true
  }
}
```

`limit` defaults to 20 and is capped at 100. When `has_more` is false,
`next_cursor` is null.

Cursors are opaque — base64 of `v1:<sort key>` — and clients must treat them as
such. The version prefix means a stale cursor from before a sort-key change
decodes to a clean 400 rather than silently addressing the wrong row.

**Why not `?page=2`.** `OFFSET 50000` makes PostgreSQL walk and throw away
50,000 rows, so deep pages get linearly slower. Worse, on a feed where new rows
arrive constantly, offsets shift under the client: page 2 re-shows items from
page 1 or skips them entirely. Keyset pagination on a ULID primary key is an
index range scan whose cost is the same at item 10 and item 500,000.

Small, bounded collections — a user's active sessions, a batch of profile
summaries — return a plain array. Pagination on a list that cannot exceed a
handful of items is ceremony.

---

## Requests

`Content-Type: application/json` for all writes. Bodies are capped at
`REQUEST_MAX_BYTES` (2 MB default) by middleware that rejects oversized
requests before they are parsed — checking after parsing is how you get an OOM
instead of a 413.

Validation is Pydantic at the boundary. Anything past the route signature is
already the right type, which is why the service layer has no defensive
`isinstance` checks in it.

### Request headers

| Header | Behaviour |
|---|---|
| `x-request-id` | Echoed if supplied, generated if not. Unique per request |
| `x-correlation-id` | Propagated unchanged across every hop and every event |

The distinction is deliberate: one request id per HTTP call, one correlation id
for the whole causal chain. Registration produces two request ids (one at auth,
one at user) and a single correlation id, which is what lets you pull the whole
handshake out of the logs with one grep.

---

## Operational endpoints

Present on every service, never under `/api/v1`:

| Endpoint | Purpose |
|---|---|
| `GET /health/live` | Is the process alive? No dependency checks. **Never** fails because PostgreSQL is down |
| `GET /health/ready` | Can it serve? Checks each registered dependency; returns 503 with a per-check breakdown if a critical one is down |
| `GET /metrics` | Prometheus text format |
| `GET /docs`, `/openapi.json` | API documentation |

The split is what makes Kubernetes behave. If liveness checked the database, a
brief PostgreSQL outage would cause the kubelet to kill and restart every pod
in the system — turning a recoverable dependency failure into a full restart
storm exactly when the database is least able to cope with a reconnect stampede.
Readiness pulls a pod out of the load balancer; liveness kills it. Only one of
those is the right response to "the database is down".

Non-critical dependencies (cache, rate limiter) report their state in the
readiness body without failing the check, because the service genuinely can
serve requests without them.

---

## Endpoint reference — built services

### auth — port 8001

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/v1/auth/register` | — | 201 with token pair. Rate limited per IP |
| POST | `/api/v1/auth/login` | — | Rate limited per IP |
| POST | `/api/v1/auth/refresh` | — | Rotates; reuse revokes all sessions |
| POST | `/api/v1/auth/logout` | — | 204. Revokes the presented refresh token |
| POST | `/api/v1/auth/logout-all` | Bearer | Revokes every session but the current |
| GET | `/api/v1/auth/me` | Bearer | Account record — email, admin flag |
| GET | `/api/v1/auth/sessions` | Bearer | Active devices, current one flagged |
| POST | `/api/v1/auth/password` | Bearer | Requires current password; revokes all sessions |

### user — port 8002

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/v1/users/me` | Bearer | Own profile |
| PATCH | `/api/v1/users/me` | Bearer | Display name, bio, location, website |
| PUT | `/api/v1/users/me/username` | Bearer | 30-day cooldown; old handle parked |
| PUT | `/api/v1/users/me/media` | Bearer | Avatar and banner media ids |
| DELETE | `/api/v1/users/me` | Bearer | 204. Soft delete |
| GET | `/api/v1/users/search` | — | Username prefix search |
| GET | `/api/v1/users/{username}` | — | Public profile |
| POST | `/internal/v1/users` | internal | Idempotent on user id. Called by auth |
| POST | `/internal/v1/users/summaries` | internal | Batch hydration — the N+1 antidote |

`/internal/v1/*` routes are not exposed through the gateway. In a deployed
setup they should additionally be restricted at the network layer — a
NetworkPolicy or security group — rather than relying on routing alone.
