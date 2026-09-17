# Failure modes

What actually happens when each dependency fails, and what the code does about
it. Verified by reading the code paths; the ones marked **untested** are
hypotheses for your chaos testing, not measurements.

---

## PostgreSQL unavailable

**Detected by:** `Database.check()` in the readiness probe, `pool_pre_ping` on
checkout.

**Behaviour:** `/health/ready` returns 503 (database is a *critical* check) so
the load balancer removes the instance. `/health/live` still returns 200, so
Kubernetes does **not** restart the pod — restarting would not help and a
restart storm during a database failover makes recovery slower. Requests in
flight fail with a 500 after `DB_POOL_TIMEOUT_SECONDS`.

**Gap:** no bulkhead between endpoints. A slow database consumes every worker,
including for endpoints that would not have touched it.

---

## PostgreSQL slow rather than down

**Behaviour:** `statement_timeout` (default 5s, set as a server setting on
every connection) kills the query. Without it a single pathological query holds
a pooled connection indefinitely and the pool drains.

**Gap:** the timeout is uniform. A deliberately long analytical query would be
killed too. Per-query overrides are the fix.

---

## Redis unavailable

**Behaviour, by use:**

| Use | Behaviour |
|---|---|
| Cache | Every operation is caught and treated as a miss. Requests are slower; results stay correct. `chirp_cache_operations_total{result="error"}` rises. |
| Rate limiting | **Fails open** — requests are allowed. See [decisions.md](decisions.md). |
| Event bus | `publish` raises `DependencyError` → 502. Workers back off exponentially to a 30s cap and resume when Redis returns. |

**Consequence:** the site stays up and reads stay correct. Writes that publish
events fail at the API level, which is visible and recoverable, rather than
silently losing the event.

**Gap:** a write that has already committed to PostgreSQL and then fails to
publish leaves the event lost. This is the outbox gap; see decisions.md.

---

## A downstream service is down

**Behaviour:** `ServiceClient` applies a 1s connect / 3s total timeout, retries
retry-safe methods (`GET`, `HEAD`, `OPTIONS`, `DELETE`) up to twice with full
jitter, and opens a circuit breaker after 5 consecutive failures. While open,
calls fail immediately with `DependencyError` rather than consuming the
caller's workers for 3 seconds each. The breaker half-opens after 10 seconds.

`POST` is **not** retried by default: it is not safe to assume it is
idempotent. Individual call sites opt in — registration does, because the user
service's create endpoint upserts on `user_id`.

**Consequence:** a dead dependency degrades one feature, not the site.
Readiness for non-critical dependencies (`HealthCheck(..., critical=False)`)
reports the failure without taking the instance out of rotation.

---

## Registration partially completes

The one genuinely distributed write in the system today. Auth writes
credentials, then calls user to create the profile.

| Failure point | State left behind | Recovery |
|---|---|---|
| User service rejects the username | Local transaction rolls back; no account | Client retries with a different username |
| User service times out after succeeding | Account not activated; profile exists | Retry is safe: the create is idempotent on `user_id` and returns the existing profile |
| Auth crashes after the user call, before activation | Account not activated; profile exists | The account cannot log in (`account_inactive`). The user re-registers and the idempotent create resolves it |
| Event publish fails after activation | Account and profile both exist and work | Downstream projections miss one `user.registered`. Nothing currently depends on it for correctness |

**Gap:** unactivated accounts accumulate. A reaper deleting them after an hour
is not implemented.

---

## Duplicate event delivery

**Cause:** normal. Redis Streams is at-least-once; a consumer that crashes
after doing work but before acknowledging will see the entry again.

**Behaviour:** `claim_event` inserts into `processed_events` in the same
transaction as the handler's writes. A duplicate hits the primary key, the
claim returns `False`, and the handler returns without repeating its effect.
Covered by `test_duplicate_delivery_is_ignored`.

---

## Poison event

**Cause:** an event whose handler always raises — a schema change, a reference
to a deleted row, a bug.

**Behaviour:** the entry is not acknowledged and stays in the pending list.
After `EVENT_CLAIM_IDLE_MS` another instance claims it via `XAUTOCLAIM`, which
increments its delivery count. At `EVENT_MAX_DELIVERY_ATTEMPTS` (5) the worker
writes it to the `chirp.events.dlq` stream and acknowledges it, so it stops
blocking the group. `chirp_events_consumed_total{outcome="dead_lettered"}`
increments.

**Gap:** nothing consumes or alerts on the DLQ. That is a deployment concern —
alert on the metric.

---

## Consumer falls behind

**Behaviour:** the stream is capped at `EVENT_MAX_STREAM_LENGTH` (100 000) with
approximate trimming. A consumer more than that far behind **silently loses
events from the head.**

**Detection:** `chirp_event_queue_depth`, reported per stream and group. Alert
well below the cap.

---

## Worker restart mid-processing

**Behaviour:** the entry was read but not acknowledged, so it stays pending and
is reclaimed after the idle window. The handler's transaction either committed
(the claim row proves it, and the redelivery is ignored) or rolled back (the
redelivery redoes it). There is no partial state.

**Untested:** the `XAUTOCLAIM` path under a real crash. Worth including in
chaos testing.

---

## Refresh token theft

**Behaviour:** refresh tokens rotate on every use. An attacker using a stolen
token rotates it; the legitimate client's next refresh presents the now-rotated
token, which is detected as reuse and revokes **every** session for the
account. Both parties are logged out and the user re-authenticates. The
revocation is committed before the error is raised — a subtle point, since the
request-scoped session would otherwise roll it back. Covered by
`test_reusing_a_rotated_token_revokes_every_session`.

---

## Clock skew between services

**Behaviour:** JWT verification allows 10 seconds of leeway. Beyond that, a
service whose clock is ahead rejects freshly minted tokens as expired.

**Mitigation:** NTP on the nodes. This is a deployment concern, listed here so
it is not a surprise when it happens.
