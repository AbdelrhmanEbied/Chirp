# auth service

Proves that a request comes from a particular user. That is the whole job.

It does not know what a username is, what a display name is, or whether the
user has ever posted. Those belong to the user service. Auth owns credentials
and sessions, and the smaller its surface the better — it is the only service
that can read password hashes.

Port 8001. Database `chirp_auth`.

---

## What it owns

**`accounts`** — email, Argon2id password hash, admin flag, `activated_at`,
`last_login_at`, `deleted_at`. `id` is a ULID and is *the* user id everywhere
in the system.

**`sessions`** — one row per logged-in device: the SHA-256 of a refresh token,
its expiry, its revocation, and `rotated_to_id` pointing at whatever replaced
it.

Schema detail in [../../docs/database.md](../../docs/database.md).

## Endpoints

| Method | Path | Auth | |
|---|---|---|---|
| POST | `/api/v1/auth/register` | — | 201 + token pair. Rate limited per IP |
| POST | `/api/v1/auth/login` | — | Rate limited per IP |
| POST | `/api/v1/auth/refresh` | — | Rotates. Reuse revokes everything |
| POST | `/api/v1/auth/logout` | — | 204. Idempotent |
| POST | `/api/v1/auth/logout-all` | Bearer | Keeps the current session |
| GET | `/api/v1/auth/me` | Bearer | |
| GET | `/api/v1/auth/sessions` | Bearer | Current session flagged |
| POST | `/api/v1/auth/password` | Bearer | Requires current password; revokes all sessions |

Plus `/health/live`, `/health/ready`, `/metrics`, `/docs`.

## The three decisions worth knowing

### Registration is a two-service handshake

There is no distributed transaction, so registration is ordered so that every
crash point leaves a recoverable state:

1. Insert the account with `activated_at = NULL`. It cannot log in.
2. `POST /internal/v1/users` on the user service — idempotent on user id, and
   retried, so a timeout that actually succeeded is safe to repeat.
3. Set `activated_at`, publish `user.registered`, return tokens.

Die after step 1 and you have a stranded account that cannot log in and whose
email is held — cleaned up by a reaper (see
[../../docs/roadmap.md](../../docs/roadmap.md)). Die after step 2 and the retry
resolves it. A username conflict at step 2 rolls the local transaction back
entirely, which is covered by `test_username_conflict_rolls_back_the_account`.

The alternative — create the profile first — is worse: it leaves a public
username belonging to no account.

### Refresh tokens are opaque, rotating, and theft-detecting

Not JWTs. Random strings, stored only as SHA-256, so a database dump yields no
usable sessions. Every refresh issues a new token and marks the old one
`rotated_to_id`.

Presenting an already-rotated token means a copy exists somewhere it should
not, so **every session for that account is revoked**. That is the only
mechanism here that turns token theft from silent into loud.

This is where a real bug lived: the revocation was written and then rolled back,
because the service raised an error afterwards and the request-scoped session
unwound the transaction with it. The control looked right in the code and did
nothing at runtime. `AuthService` now takes the session explicitly and commits
the revocation before raising.

### Access tokens are verified locally, everywhere

HS256 JWTs, minted only here, verified by every other service with the shared
secret. No network call, no shared session store, no introspection endpoint.
Auth is therefore not on the hot path of any request except login and can be
the smallest deployment in the cluster.

The cost: **an access token cannot be revoked before it expires.** Logging out
kills the refresh token, so nothing new can be minted, but the token already
issued stays valid for up to fifteen minutes. That is why the TTL is short.

`HS256` with a shared secret also means every service *could* mint tokens, not
just verify them. Acceptable locally, not acceptable deployed. `JWTCodec` takes
the algorithm as configuration so RS256 with a JWKS endpoint is a small change.

## Security specifics

- **Argon2id** via `argon2-cffi`, with `needs_rehash` on login so parameters can
  be raised later without a migration.
- **Timing equalisation**: an unknown email still runs a hash verification
  against a dummy hash. Otherwise response latency is an email enumeration
  oracle.
- **Identical errors** for unknown email and wrong password.
- **Session cap** per account, evicting oldest first.
- **Rate limits** on login and registration, per IP, in Redis. Fail-open — if
  Redis is down requests are allowed rather than the service being down. That
  is a deliberate availability-over-security trade for a limiter that exists to
  slow brute force, and it is noted in
  [../../docs/failure-modes.md](../../docs/failure-modes.md).

None of this makes the service production-secure. It has had no security review,
no penetration testing, and no threat model written against it.

## Events

Publishes `user.registered`. Consumes nothing.

## Configuration

Beyond the shared variables in `.env.example`:

| Variable | Default | |
|---|---|---|
| `USER_SERVICE_URL` | `http://user:8002` | Registration handshake target |
| `REFRESH_TOKEN_TTL_SECONDS` | 2592000 | 30 days |
| `MAX_ACTIVE_SESSIONS_PER_USER` | 10 | |
| `LOGIN_RATE_LIMIT` / `LOGIN_RATE_WINDOW_SECONDS` | 10 / 60 | |
| `REGISTER_RATE_LIMIT` / `REGISTER_RATE_WINDOW_SECONDS` | 5 / 3600 | |

## Layout

```
app/
  main.py          create_app + lifespan + health checks
  settings.py      environment-derived configuration
  dependencies.py  composition root; everything injected from here
  routes.py        HTTP only, no logic
  service.py       domain logic, no SQL, no HTTP
  repository.py    SQL only
  models.py        accounts, sessions
  schemas.py       request/response contracts
migrations/        this service's own Alembic history
tests/             25 tests
```

## Tests

```bash
cd services/auth && python3 -m pytest -q          # 25 passed
```

Worth reading: `test_refresh_rotation.py` for the theft-detection behaviour,
`test_registration.py` for both directions of the handshake.

## Running standalone

```bash
docker compose up -d postgres redis
cd services/auth
export DATABASE_URL="postgresql+asyncpg://chirp:chirp-local-password@localhost:5432/chirp_auth"
export REDIS_URL="redis://localhost:6379/0"
export EVENT_BUS_URL="redis://localhost:6379/1"
export JWT_SECRET="<the value from .env>"
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

Use the `JWT_SECRET` from `.env` if you want tokens minted here to verify in the
containerised services.
