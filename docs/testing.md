# Testing

44 tests today: 25 in auth, 19 in user. Every one of them asserts behaviour that
could plausibly break. There are no tests that import a module and assert it
imported, and no tests written to move a coverage number.

```bash
make install            # editable installs first
make test               # both suites, SQLite, ~3 seconds, no containers
make test-integration   # same suites against PostgreSQL in Compose
```

Per service:

```bash
cd services/auth && python3 -m pytest -q
cd services/auth && python3 -m pytest tests/test_refresh_rotation.py -vv
```

## What gets a test

The rule is: anything where being wrong is expensive and being wrong is
plausible. In practice that is four categories.

**Security invariants.** These are the tests to read first, because they encode
decisions rather than mechanics.

- `test_reusing_a_rotated_token_revokes_every_session` — presenting an
  already-exchanged refresh token means a copy exists somewhere it should not,
  so every session for that account dies. This test caught a real bug: the
  revocation was being written and then rolled back, because the service raised
  an error and the request-scoped session unwound the transaction with it. The
  security control looked correct in the code and did nothing at runtime. The
  fix was to commit the revocation explicitly before raising.
- `test_login_for_unknown_email_gives_the_same_error` — an unknown email and a
  wrong password return the same response, and the unknown-email path still
  runs a hash verification against a dummy hash so the timing matches. Without
  that, response latency is an email enumeration oracle.
- `test_me_requires_a_token`, `test_update_profile_requires_auth` — the
  authorisation check is present, not assumed.
- `test_old_username_cannot_be_claimed_by_someone_else` — the impersonation
  path after a username change.
- `test_reserved_usernames_are_refused` — nobody registers `admin`.

**Cross-service handshakes.** `test_register_returns_tokens_and_creates_profile`
and `test_username_conflict_rolls_back_the_account` cover the two-step
registration in both directions. The second matters more: when the user service
rejects the username, the account row must not survive, because a stranded
unactivated account holds the email address hostage.

**Event handling.** `test_duplicate_delivery_is_ignored` feeds the same event
envelope to the projector twice and asserts the counter moved once — the
at-least-once guarantee means this is not a hypothetical.
`test_unfollow_decrements_and_never_goes_negative` covers the clamp, because
duplicate decrements are the realistic way counters go wrong.

**Boundaries and edges.** Cooldown windows on both sides
(`test_cooldown_blocks_a_second_change`, `test_cooldown_expires`), idempotent
operations called twice (`test_logout_is_idempotent`,
`test_create_profile_is_idempotent`), the session cap evicting oldest-first,
case-insensitive lookups, prefix search, and validation rejecting a
`javascript:` website.

## What does not get a test

Pydantic validating its own field types. SQLAlchemy emitting SQL. FastAPI
routing. Getters. Those are other people's test suites, and duplicating them
produces a suite that is slow to run and expensive to change without ever
catching a defect.

## How the harness works

Tests exercise services through **HTTP against the real ASGI app** —
`httpx.AsyncClient` over `ASGITransport`, no network — rather than by calling
service methods directly. That means middleware, dependency injection,
validation, serialisation and error handlers are all in the path. A test that
calls `AuthService.login()` directly proves the method works and proves nothing
about whether the endpoint is wired up, which is a class of bug that reaches
production easily.

`conftest.py` provides:

- `settings` — a real settings object with test values, no environment reading
- `context` — the composition root: SQLite database with tables created,
  `InMemoryEventBus`, `NullCache`, a `JWTCodec` on the shared test secret
- `client` — an `AsyncClient` bound to a freshly built app
- helper fixtures for a registered user and a valid token

Every fixture is function-scoped. Each test gets an empty database.

Substituting the cache and bus is deliberate. `NullCache` means tests exercise
the uncached path, which is the path that has to be correct — a cache that
returns nothing must never change an answer, and using a real cache in tests
would let a caching bug hide behind a hit. `InMemoryEventBus` collects published
envelopes so a test can assert `user.profile_updated` was published with the
right subject id, without a broker.

## SQLite for unit tests, PostgreSQL for integration

Unit tests run on in-memory SQLite with a `StaticPool` so every connection sees
the same database. The whole suite is about three seconds, which is what makes
running tests on every save realistic.

SQLite is not PostgreSQL, and the gaps have already produced bugs — which is
the argument for `make test-integration` existing rather than for abandoning
SQLite:

- **Timezones.** SQLite returns naive datetimes where PostgreSQL returns
  aware ones. Comparing them raises `TypeError`. That is why
  `chirp_common.timeutil.ensure_utc` exists and is used at every comparison.
- **`ON CONFLICT ... RETURNING`.** Supported by both but with different
  behaviour at the edges; `claim_event` has an explicit fallback path.
- **`GREATEST`.** Does not exist in SQLite, so the counter clamp is a `CASE`.
- **Autoincrement.** A `BigInteger` primary key that PostgreSQL happily made a
  sequence for simply failed on SQLite — which is why `UsernameHistory` uses a
  ULID like everything else. The SQLite failure pushed the schema toward the
  more consistent design.

```bash
TEST_DATABASE_URL="postgresql+asyncpg://chirp:chirp-local-password@localhost:5432/chirp_test" \
  python3 -m pytest -q
```

Same tests, same assertions, one environment variable. `make test-integration`
does this against the Compose PostgreSQL.

## What is not covered yet

Stated plainly, because a testing document that only lists strengths is
marketing.

- **No end-to-end test across running containers.** The registration handshake
  is tested with the user service's HTTP client stubbed. Nothing currently
  asserts that two real containers complete it over a real network. That is the
  most valuable missing test.
- **No load or soak testing.** Deliberately out of scope — it is infrastructure
  work and it needs a deployed environment to mean anything.
- **No chaos testing.** [failure-modes.md](failure-modes.md) reasons about what
  happens when Redis dies; it does not prove it by killing Redis. The
  degradation paths (`NullCache`, fail-open rate limiting) are unit tested; the
  real behaviour under a mid-request failure is not.
- **No property-based tests.** Cursor encode/decode and the ULID generator are
  the obvious candidates for Hypothesis.
- **No migration tests.** Nothing asserts that `upgrade` then `downgrade` leaves
  the schema where it started.

## Linting and types

```bash
make lint      # ruff check + ruff format --check + mypy
make format    # ruff format + ruff check --fix
```

Ruff with `E,F,W,I,B,UP,ASYNC,S,C4,SIM,RET,TID` at a 96-character line length.
`ASYNC` catches blocking calls inside async functions — the defect that makes a
service mysteriously slow under concurrency while every unit test passes. `S`
is Bandit's security rules. `TID` bans relative imports across package
boundaries.

mypy runs in strict-ish mode over `libs/` and `services/`. Tests are excluded:
strict typing on fixtures costs more than it catches.
