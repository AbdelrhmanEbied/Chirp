# Chirp Architecture — Complete Reference

## Table of Contents

- [1. Overview](#1-overview)
- [2. High-Level Architecture](#2-high-level-architecture)
- [3. Services Deep Dive](#3-services-deep-dive)
- [4. Inter-Service Communication](#4-inter-service-communication)
- [5. Event Bus (Redis Streams)](#5-event-bus-redis-streams)
- [6. Database Architecture](#6-database-architecture)
- [7. Timeline Fan-Out Architecture](#7-timeline-fan-out-architecture)
- [8. Search Architecture (FTS + Trigram)](#8-search-architecture-fts--trigram)
- [9. Media Storage Flow](#9-media-storage-flow)
- [10. Authentication & Authorization](#10-authentication--authorization)
- [11. Middleware Stack](#11-middleware-stack)
- [12. Infrastructure (AWS)](#12-infrastructure-aws)
- [13. Kubernetes Architecture](#13-kubernetes-architecture)
- [14. IAM Roles & Policies](#14-iam-roles--policies)
- [15. Networking & Security](#15-networking--security)
- [16. Monitoring & Observability](#16-monitoring--observability)
- [17. CI/CD Pipeline](#17-cicd-pipeline)
- [18. Request Flow Diagrams](#18-request-flow-diagrams)

---

## 1. Overview

Chirp is a Twitter-like microservices platform designed for ~1M users. It consists of **11 microservices**, each owning its own PostgreSQL database, communicating via HTTP (synchronous) and Redis Streams (asynchronous events).

### Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Service communication | HTTP + Redis Streams | HTTP for sync queries, events for async side effects |
| Database | PostgreSQL per service | Service data isolation, independent scaling |
| Event bus | Redis Streams | At-least-once delivery, consumer groups, no extra infra |
| Timeline | Fan-out-on-write | O(1) feed reads, acceptable write amplification |
| Search | FTS + trigram | Combined exact and fuzzy matching |
| Auth | HS256 JWT | Local verification by every service, no auth bottleneck |
| Deployment | EKS + RDS + ElastiCache | Managed services, production-ready |

---

## 2. High-Level Architecture

```
                              INTERNET
                                 |
                    +------------v------------+
                    |     CloudFront CDN      |
                    |   (Frontend SPA only)   |
                    +------------+------------+
                                 |
                    +------------v------------+
                    |    AWS ALB (HTTPS:443)  |
                    |  SSL termination + WAF  |
                    +--+------------------+---+
                       |                  |
              +--------v--------+  +------v------+
              |  Gateway :8000  |  | Media :8009 |
              |  (BFF + Rate    |  | (File API)  |
              |   Limiting)     |  +------+------+-------+
              +--------+--------+         |              |
                       |             +----v----+    +----v----+
          +------------+---+         |  S3     |    | CloudFront|
          |   |   |   |   |         | (media) |    | (files)  |
          v   v   v   v   v         +---------+    +----------+
        Auth User Post Graph
       :8001 :8002 :8003 :8004
          |   |   |   |
          v   v   v   v
       Timeline Search Notification Messaging Moderation
       :8005    :8006    :8007      :8008     :8010
                       |
              +--------v--------+
              |  Redis Streams  |
              |  (Event Bus)    |
              +--------+--------+
                       |
        +--------------+--------------+
        |         |         |         |
     Timeline  Search   Notif    User/Post
      Worker   Worker   Worker   Workers
        |         |         |         |
        v         v         v         v
     PostgreSQL 16.4 (RDS Multi-AZ)
     10 databases, one per service
```

### Component Summary

| Component | Count | Purpose |
|-----------|-------|---------|
| API Services | 11 | Handle HTTP requests |
| Workers | 5 | Process async events |
| Databases | 10 | One PostgreSQL DB per service |
| Redis | 3 nodes | Cache + Event bus + Rate limiting |
| S3 Buckets | 2 | Media storage + Frontend SPA |
| EKS Nodes | 3-10 | Kubernetes worker nodes |

---

## 3. Services Deep Dive

### 3.1 Gateway Service (port 8000)

**Role**: Backend-for-Frontend (BFF). Single entry point for all client requests.

```
Client --> Gateway --> Auth Service
                   --> User Service
                   --> Post Service
                   --> Graph Service
                   --> Timeline Service
                   --> Search Service
                   --> Notification Service
                   --> Messaging Service
```

**Responsibilities**:
- Route requests to correct downstream service
- Enforce rate limiting (per client IP, Redis-based)
- Aggregate responses (e.g., feed = timeline + users + posts)
- CORS handling
- Request/response logging

**Routes**:

| Method | Path | Proxied To | Auth |
|--------|------|------------|------|
| POST | `/api/v1/auth/register` | auth:8001 | No |
| POST | `/api/v1/auth/login` | auth:8001 | No |
| GET | `/api/v1/users/me` | user:8002 | Yes |
| PATCH | `/api/v1/users/me` | user:8002 | Yes |
| POST | `/api/v1/posts` | post:8003 | Yes |
| GET | `/api/v1/feed` | timeline + user + post | Yes |
| GET | `/api/v1/search` | search:8006 | Yes |
| POST | `/api/v1/media` | media:8009 | Yes |

**No database** — purely a proxy/aggregator.

---

### 3.2 Auth Service (port 8001)

**Role**: Owns credentials and sessions. Mints JWT tokens.

**Database**: `chirp_auth`

**Tables**:
- `users` — id, email, username, hashed_password, is_active, created_at
- `sessions` — id, user_id, refresh_token, expires_at, created_at
- `processed_events` — event_id, processed_at (idempotency)

**Key Operations**:
- `POST /api/v1/auth/register` — Hash password (Argon2id, 256MB), create user, publish `USER_REGISTERED` event
- `POST /api/v1/auth/login` — Verify password, create session, return access + refresh tokens
- `POST /api/v1/auth/refresh` — Validate refresh token, mint new access token
- `POST /api/v1/auth/logout` — Invalidate session

**JWT Configuration**:
- Algorithm: HS256
- Access token TTL: 15 minutes
- Refresh token TTL: 30 days
- Claims: `user_id`, `session_id`, `scopes`, `iss`, `aud`, `exp`, `iat`

---

### 3.3 User Service (port 8002)

**Role**: Owns public profiles and denormalized social counters.

**Database**: `chirp_user`

**Tables**:
- `users` — id, username, display_name, bio, avatar_url, is_verified, created_at
- `user_counters` — user_id, followers_count, following_count, posts_count (denormalized)
- `processed_events` — event_id, processed_at

**Key Operations**:
- `GET /api/v1/users/{id}` — Fetch public profile
- `PATCH /api/v1/users/me` — Update display name, bio, avatar
- `POST /internal/v1/users/summaries` — Batch fetch user summaries (for feed hydration)
- Worker: Consumes `POST_CREATED`, `POST_DELETED`, `USER_FOLLOWED`, `USER_UNFOLLOWED` to update counters

---

### 3.4 Post Service (port 8003)

**Role**: Owns posts, likes, reposts, bookmarks.

**Database**: `chirp_post`

**Tables**:
- `posts` — id, author_id, text, media_ids, reply_to, quote_of, created_at
- `likes` — user_id, post_id, created_at
- `reposts` — user_id, post_id, created_at
- `bookmarks` — user_id, post_id, created_at
- `processed_events` — event_id, processed_at

**Key Operations**:
- `POST /api/v1/posts` — Create post, publish `POST_CREATED` event
- `DELETE /api/v1/posts/{id}` — Delete post, publish `POST_DELETED` event
- `POST /api/v1/posts/{id}/like` — Like post, publish `POST_LIKED` event
- `DELETE /api/v1/posts/{id}/like` — Unlike post, publish `POST_UNLIKED` event
- `POST /internal/v1/posts/batch` — Batch fetch posts (for feed hydration)
- `GET /internal/v1/posts/by/{user_id}` — Fetch user's posts (for timeline backfill)
- Worker: Consumes `USER_DELETED` to remove all user's posts, `USER_FOLLOWED` to update counters

---

### 3.5 Graph Service (port 8004)

**Role**: Manages social graph — follows, blocks, mutes.

**Database**: `chirp_graph`

**Tables**:
- `follows` — follower_id, following_id, created_at
- `blocks` — blocker_id, blocked_id, created_at
- `mutes` — muter_id, muted_id, created_at

**Key Operations**:
- `POST /api/v1/graph/{user_id}/follow` — Follow user, publish `USER_FOLLOWED` event
- `DELETE /api/v1/graph/{user_id}/follow` — Unfollow user, publish `USER_UNFOLLOWED` event
- `GET /internal/v1/graph/{user_id}/followers?limit=N` — Fetch follower IDs (for timeline fan-out)
- `GET /internal/v1/graph/{user_id}/following` — Fetch following IDs
- `GET /internal/v1/graph/{user_id}/is-following/{target_id}` — Check follow relationship

---

### 3.6 Timeline Service (port 8005)

**Role**: Assembles home and user timelines. Uses fan-out-on-write for home feed.

**Database**: `chirp_timeline`

**Tables**:
- `feed_entries` — id, user_id, post_id, author_id, text, likes_count, reposts_count, replies_count, created_at
- `processed_events` — event_id, processed_at

**Key Operations**:
- `GET /api/v1/feed` — Read pre-materialized home feed (O(1) lookup)
- `GET /api/v1/users/{user_id}/timeline` — Fetch user's posts from post service (not pre-materialized)
- Worker: Fan-out-on-write projector (see [Section 7](#7-timeline-fan-out-architecture))

---

### 3.7 Search Service (port 8006)

**Role**: Full-text search indexing for posts and hashtags.

**Database**: `chirp_search`

**Tables**:
- `post_search` — post_id, author_id, text, created_at_index
- `hashtag_usage` — hashtag, usage_count
- `processed_events` — event_id, processed_at

**Key Operations**:
- `GET /api/v1/search?q={query}&sort=relevance` — Search posts using FTS + trigram
- `GET /api/v1/hashtags/trending` — Top hashtags by usage count
- Worker: Indexes posts on `POST_CREATED`, removes on `POST_DELETED`

---

### 3.8 Notification Service (port 8007)

**Role**: Event-driven notification creation.

**Database**: `chirp_notification`

**Tables**:
- `notifications` — id, user_id, type, actor_id, reference_id, read, created_at
- `processed_events` — event_id, processed_at

**Worker Subscriptions**:
- `POST_LIKED` — Notify post author
- `REPLY_CREATED` — Notify parent post author
- `QUOTE_CREATED` — Notify quoted post author
- `USER_MENTIONED` — Notify mentioned user
- `USER_FOLLOWED` — Notify followed user
- `MESSAGE_SENT` — Notify message recipient

---

### 3.9 Messaging Service (port 8008)

**Role**: Direct messaging between users.

**Database**: `chirp_messaging`

**Tables**:
- `conversations` — id, created_at, updated_at
- `conversation_participants` — conversation_id, user_id, user_id
- `messages` — id, conversation_id, sender_id, text, created_at
- `processed_events` — event_id, processed_at

**Key Operations**:
- `POST /api/v1/messages/{user_id}` — Send DM (verifies follow relationship via graph service)
- `GET /api/v1/messages` — List conversations
- `GET /api/v1/messages/{conversation_id}` — Fetch message history

---

### 3.10 Media Service (port 8009)

**Role**: Media upload, serving, and deletion.

**Database**: `chirp_media`

**Tables**:
- `media` — id, owner_id, content_type, file_size, storage_key, state, width, height, created_at

**Key Operations**:
- `POST /api/v1/media` — Upload file (magic-byte content-type sniffing)
- `GET /files/{key}` — Serve media file
- `DELETE /api/v1/media/{id}` — Delete media file

**Storage Backends**:
- **Local**: Writes to `/srv/uploads/` (development only)
- **S3**: Uploads to `chirp-prod-media` bucket (production)

---

### 3.11 Moderation Service (port 8010)

**Role**: Content reporting and admin actions.

**Database**: `chirp_moderation`

**Tables**:
- `reports` — id, reporter_id, content_type, content_id, reason, status, created_at
- `actions` — id, report_id, moderator_id, action_type, created_at

---

## 4. Inter-Service Communication

### 4.1 HTTP (Synchronous)

All service-to-service HTTP calls use the shared `ServiceClient` from `chirp-common`:

```
ServiceClient Features:
├── Connection pooling (64 max, 16 keepalive)
├── Circuit breaker (5 failures -> open, 10s reset)
├── Exponential backoff retry (max 2 retries)
├── Retryable status codes: 502, 503, 504
├── Request ID + Correlation ID propagation
└── Per-service timeout (5s default)
```

**Internal API Endpoints** (`/internal/v1/...`):

| Caller | Callee | Endpoint | Purpose |
|--------|--------|----------|---------|
| gateway | user | `POST /internal/v1/users/summaries` | Batch fetch for feed |
| gateway | post | `POST /internal/v1/posts/batch` | Batch fetch for feed |
| timeline | graph | `GET /internal/v1/graph/{id}/followers` | Fan-out follower list |
| timeline | post | `GET /internal/v1/posts/by/{user_id}` | Backfill on follow |
| timeline | user | `POST /internal/v1/users/summaries` | Hydrate feed authors |
| messaging | graph | `GET /internal/v1/graph/{id}/is-following/{target}` | Verify DM eligibility |
| search | user | `POST /internal/v1/users/summaries` | User search results |
| post | user | `POST /internal/v1/users/summaries` | Author hydration |

### 4.2 Events (Asynchronous via Redis Streams)

**Stream Naming**: `chirp.events.{event_type}`

**Consumer Pattern**:
```
Consumer Group: {service}-worker
├── Load balancing: Messages distributed across worker replicas
├── Acknowledgment: Manual ACK after successful processing
├── Dead Letter: Messages re-queued up to 5 times, then sent to DLQ
└── Idempotency: processed_events table prevents duplicate processing
```

---

## 5. Event Bus (Redis Streams)

### 5.1 Event Envelope

Every event follows this structure:

```json
{
  "id": "01HXYZ...",
  "type": "post.created",
  "version": 1,
  "producer": "post-service",
  "subject_id": "post-uuid",
  "actor_id": "user-uuid",
  "occurred_at": "2026-09-18T10:00:00Z",
  "correlation_id": "request-uuid",
  "causation_id": "event-uuid",
  "payload": {
    "post_id": "post-uuid",
    "author_id": "user-uuid",
    "text": "Hello world",
    "media_ids": [],
    "reply_to": null,
    "quote_of": null
  }
}
```

### 5.2 All Event Types

#### User Events

| Event | Producer | Payload Key Fields | Consumed By |
|-------|----------|-------------------|-------------|
| `user.registered` | auth | user_id, email, username | user-worker |
| `user.profile_updated` | user | user_id, changes | — |
| `user.deleted` | user | user_id | post-worker |

#### Post Events

| Event | Producer | Payload Key Fields | Consumed By |
|-------|----------|-------------------|-------------|
| `post.created` | post | post_id, author_id, text | timeline-worker, search-worker |
| `post.deleted` | post | post_id, author_id | timeline-worker, search-worker |
| `post.liked` | post | post_id, author_id, user_id | notification-worker |
| `post.unliked` | post | post_id, user_id | — |
| `post.reposted` | post | post_id, user_id | — |
| `post.unreposted` | post | post_id, user_id | — |
| `post.reply_created` | post | post_id, reply_to, author_id | notification-worker |
| `post.quote_created` | post | post_id, quote_of, author_id | notification-worker |
| `post.user_mentioned` | post | post_id, mentioned_user_id | notification-worker |
| `post.hashtag_used` | post | post_id, hashtag | search-worker |

#### Graph Events

| Event | Producer | Payload Key Fields | Consumed By |
|-------|----------|-------------------|-------------|
| `graph.user_followed` | graph | follower_id, following_id | timeline-worker, user-worker |
| `graph.user_unfollowed` | graph | follower_id, following_id | timeline-worker, user-worker |
| `graph.user_blocked` | graph | blocker_id, blocked_id | — |
| `graph.user_unblocked` | graph | blocker_id, blocked_id | — |

#### Other Events

| Event | Producer | Payload Key Fields | Consumed By |
|-------|----------|-------------------|-------------|
| `messaging.message_sent` | messaging | message_id, sender_id, recipient_id | notification-worker |
| `moderation.report_created` | moderation | report_id, content_type | — |
| `moderation.content_actioned` | moderation | action_id, content_type | — |
| `media.uploaded` | media | media_id, owner_id | — |
| `media.deleted` | media | media_id | — |

### 5.3 Dead Letter Queue

```
Message fails processing
  -> Re-queue (up to 5 attempts)
    -> Still failing?
      -> Move to chirp.events.dlq
        -> Manual inspection required
```

---

## 6. Database Architecture

### 6.1 Single RDS Instance, 10 Databases

All services share one PostgreSQL 16.4 RDS instance but each has its own logical database. This provides:
- Data isolation (no cross-service queries)
- Independent migrations per service
- Cost efficiency vs. 10 separate RDS instances

### 6.2 Database Map

| Database | Service | Key Tables |
|----------|---------|------------|
| `chirp_auth` | auth | users, sessions, processed_events |
| `chirp_user` | user | users, user_counters, processed_events |
| `chirp_post` | post | posts, likes, reposts, bookmarks, processed_events |
| `chirp_graph` | graph | follows, blocks, mutes |
| `chirp_timeline` | timeline | feed_entries, processed_events |
| `chirp_search` | search | post_search, hashtag_usage, processed_events |
| `chirp_notification` | notification | notifications, processed_events |
| `chirp_messaging` | messaging | conversations, conversation_participants, messages, processed_events |
| `chirp_media` | media | media |
| `chirp_moderation` | moderation | reports, actions |

### 6.3 Connection Pooling

Each service uses `asyncpg` with configurable pool settings:
- `DB_POOL_MIN_SIZE`: Minimum connections (default: 2)
- `DB_POOL_MAX_SIZE`: Maximum connections (default: 10)
- `DB_APPLICATION_NAME`: Per-service identifier for PostgreSQL `pg_stat_activity`

### 6.4 Idempotency

Every service that processes events has a `processed_events` table:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

Before processing an event, the worker checks if `event_id` already exists. After processing, it inserts the `event_id`. Both operations happen in the same transaction.

---

## 7. Timeline Fan-Out Architecture

The timeline uses a **push-based fan-out-on-write** model for the home feed.

### 7.1 Post Creation Flow

```
1. User creates post
   |
   v
2. Post Service creates DB record
   |
   v
3. Post Service publishes POST_CREATED event to Redis
   |
   v
4. Timeline Worker consumes event
   |
   v
5. Fetch all follower IDs from Graph Service
   GET /internal/v1/graph/{author_id}/followers?limit=50000
   |
   v
6. Celebrity Check:
   - If author has >= 10,000 followers -> SKIP fan-out (lazy read)
   - Otherwise -> continue
   |
   v
7. Active Follower Filter:
   - Only fans out to followers active in last 7 days
   - OR followers who already have feed entries
   |
   v
8. Create FeedEntry for each active follower:
   INSERT INTO feed_entries (user_id, post_id, author_id, text, ...)
   |
   v
9. Cap feed size at 800 entries per user
   (delete oldest if exceeded)
```

### 7.2 Follow Flow

```
1. User A follows User B
   |
   v
2. Graph Service publishes USER_FOLLOWED event
   |
   v
3. Timeline Worker consumes event
   |
   v
4. Fetch User B's 50 most recent posts
   GET /internal/v1/posts/by/{user_b_id}?limit=50
   |
   v
5. Insert these posts into User A's feed_entries
```

### 7.3 Unfollow Flow

```
1. User A unfollows User B
   |
   v
2. Graph Service publishes USER_UNFOLLOWED event
   |
   v
3. Timeline Worker consumes event
   |
   v
4. DELETE FROM feed_entries
   WHERE user_id = 'user_a' AND author_id = 'user_b'
```

### 7.4 Post Deletion Flow

```
1. Post author deletes post
   |
   v
2. Post Service publishes POST_DELETED event
   |
   v
3. Timeline Worker consumes event
   |
   v
4. DELETE FROM feed_entries WHERE post_id = '{deleted_post_id}'
   (removes from ALL users' feeds)
```

### 7.5 Read Path

```
GET /api/v1/feed
   |
   v
1. Timeline Service reads from feed_entries table
   WHERE user_id = ? ORDER BY created_at DESC LIMIT 20
   |
   v
2. Gateway batch-fetches author summaries from User Service
   POST /internal/v1/users/summaries { "user_ids": [...] }
   |
   v
3. Gateway batch-fetches full posts from Post Service
   POST /internal/v1/posts/batch { "post_ids": [...] }
   |
   v
4. Gateway merges and returns hydrated feed
```

---

## 8. Search Architecture (FTS + Trigram)

### 8.1 Indexing Flow

```
POST_CREATED event
   |
   v
Search Worker consumes event
   |
   v
INSERT INTO post_search (post_id, author_id, text)
   |
   v
(If hashtags found) UPDATE hashtag_usage
   SET usage_count = usage_count + 1
   WHERE hashtag = ?
```

### 8.2 Search Query (PostgreSQL)

The search repository uses three strategies based on the `sort` parameter:

#### Relevance (default)
```sql
SELECT post_id, author_id, text,
       ts_rank(text_search, plainto_tsquery('english', $1)) AS rank,
       similarity(text, $1) AS sim
FROM post_search
WHERE text_search @@ plainto_tsquery('english', $1)
   OR similarity(text, $1) > 0.2
ORDER BY (rank + sim * 0.5) DESC
LIMIT 20 OFFSET 0;
```

#### Recent
```sql
SELECT post_id, author_id, text
FROM post_search
WHERE text_search @@ plainto_tsquery('english', $1)
   OR similarity(text, $1) > 0.2
ORDER BY created_at_index DESC
LIMIT 20 OFFSET 0;
```

#### Similarity
```sql
SELECT post_id, author_id, text,
       similarity(text, $1) AS sim
FROM post_search
WHERE similarity(text, $1) > 0.1
ORDER BY sim DESC
LIMIT 20 OFFSET 0;
```

### 8.3 SQLite Fallback

For local development without PostgreSQL extensions:
```sql
SELECT * FROM post_search
WHERE text LIKE '%{query}%'
ORDER BY created_at_index DESC;
```

---

## 9. Media Storage Flow

### 9.1 Upload Flow

```
1. Client sends POST /api/v1/media with file
   |
   v
2. Content-Type Sniffing (magic bytes):
   - FF D8 FF    -> image/jpeg
   - 89 50 4E 47 -> image/png
   - GIF87a/89a  -> image/gif
   - RIFF...WEBP -> image/webp
   - ....        -> video/mp4, application/pdf, etc.
   |
   v
3. Validation:
   - File size <= media_max_size_bytes
   - Content type in allowed list
   - Image dimensions within limits
   |
   v
4. Storage:
   - Key: {ulid}{extension} (e.g., 01HXYZ...jpg)
   - Local: Write to /srv/uploads/
   - S3: Upload to chirp-prod-media bucket
   |
   v
5. Database: INSERT INTO media (id, owner_id, content_type, storage_key, ...)
   |
   v
6. Response: { "id": "...", "url": "/files/01HXYZ...jpg" }
```

### 9.2 S3 Configuration

| Setting | Value |
|---------|-------|
| Bucket | chirp-prod-media |
| Versioning | Enabled |
| Encryption | AES256 (SSE-S3) |
| Public Access | Blocked |
| Lifecycle | Standard-IA after 90 days, Glacier after 180 days |
| CORS | Restricted to frontend domain |

---

## 10. Authentication & Authorization

### 10.1 JWT Flow

```
1. Client registers/logs in
   |
   v
2. Auth Service validates credentials
   |
   v
3. Auth Service mints JWT:
   {
     "user_id": "...",
     "session_id": "...",
     "scopes": ["read", "write"],
     "iss": "chirp-auth",
     "aud": "chirp-api",
     "exp": now + 15min,
     "iat": now
   }
   |
   v
4. Auth Service signs with HS256(secret)
   |
   v
5. Client stores token, sends in Authorization header
   |
   v
6. Every service verifies locally (no network call to auth)
```

### 10.2 FastAPI Dependencies

```python
# Required authentication
current_user: CurrentUser = Depends(get_current_user)

# Optional authentication (public endpoints with optional user context)
user: OptionalUser = Depends(get_optional_user)

# Admin-only
admin: CurrentUser = Depends(require_admin)  # checks "admin" in scopes
```

### 10.3 Token Refresh

```
Access token expires (15min)
   |
   v
Client sends refresh token to POST /api/v1/auth/refresh
   |
   v
Auth Service validates refresh token (30 day TTL)
   |
   v
Returns new access token + refresh token
```

---

## 11. Middleware Stack

Every FastAPI service applies this middleware chain (in order):

### 11.1 Request Context Middleware
- Extracts/generates `X-Request-ID` and `X-Correlation-ID`
- Binds to async context for logging
- Returns in response headers

### 11.2 CORS Middleware
```
Origins: Configurable (CORS_ORIGINS env var)
Methods: GET, POST, PATCH, PUT, DELETE, OPTIONS
Headers: authorization, content-type, X-Correlation-ID
Exposed: X-Request-ID, X-Correlation-ID
Max Age: 600 seconds
Credentials: Allowed
```

### 11.3 Body Size Limit Middleware
- Max request body: 2 MB (`REQUEST_MAX_BYTES`)
- Returns HTTP 413 if exceeded

### 11.4 Rate Limiting Middleware (Gateway only)
```
Algorithm: Sliding window (INCR + EXPIRE in Redis pipeline)
Key: ratelimit:{scope}:{client_ip}:{window_bucket}
Scope: gateway_rate_limit / gateway_rate_window_seconds
Failure mode: Fail-open (allows if Redis unavailable)
Response: HTTP 429 with Retry-After header
```

### 11.5 Access Logging Middleware
- Logs: service, method, path, route template, status, duration
- Skips: /metrics, /health/live, /health/ready
- Prometheus metrics: `http_requests_total`, `http_request_duration_seconds`

### 11.6 Error Handling
- `AppError` -> Custom status code + structured JSON
- `RateLimitedError` -> 429 with Retry-After
- `RequestValidationError` -> 422 with field details
- Unhandled exceptions -> 500 with request ID

---

## 12. Infrastructure (AWS)

### 12.1 VPC

```
VPC: 10.0.0.0/16
├── Public Subnets (for ALB)
│   ├── 10.0.101.0/24 (AZ-a)
│   ├── 10.0.102.0/24 (AZ-b)
│   └── 10.0.103.0/24 (AZ-d)
├── Private Subnets (for EKS, RDS, Redis)
│   ├── 10.0.1.0/24 (AZ-a)
│   ├── 10.0.2.0/24 (AZ-b)
│   └── 10.0.3.0/24 (AZ-d)
├── Internet Gateway
├── NAT Gateway (single, for cost)
├── Route Tables
│   ├── Public -> IGW (0.0.0.0/0)
│   └── Private -> NAT (0.0.0.0/0)
└── Security Groups
    ├── EKS Cluster SG
    ├── EKS Node SG
    ├── RDS SG (5432 from EKS Node SG)
    └── Redis SG (6379 from EKS Node SG)
```

### 12.2 EKS

```
Cluster: chirp-prod (Kubernetes 1.31)
├── Endpoint: Public + Private
├── Node Group: general
│   ├── Instance: m6i.xlarge (4 vCPU, 16GB)
│   ├── Desired: 3, Min: 2, Max: 10
│   ├── Capacity: ON_DEMAND
│   └── Autoscaler: Enabled
├── Addons
│   ├── CoreDNS
│   ├── kube-proxy
│   ├── VPC CNI
│   └── EBS CSI Driver (IRSA)
└── IRSA: Enabled (pod-level IAM)
```

### 12.3 RDS

```
Instance: db.t3.micro (free tier) / db.r6g.xlarge (prod)
├── Engine: PostgreSQL 16.4
├── Multi-AZ: Yes
├── Storage: 20 GB (auto-scale to 100 GB)
├── Backup: 1 day retention
├── Encryption: At-rest (default)
├── Performance Insights: Enabled
├── Deletion Protection: Yes
├── Security Group: 5432 from EKS Node SG only
└── 10 Logical Databases: chirp_auth, chirp_user, chirp_post, ...
```

### 12.4 ElastiCache (Redis)

```
Cluster: chirp-prod
├── Engine: Redis 7.0
├── Node: cache.r6g.large (2 vCPU, 13GB)
├── Nodes: 3 (replication group)
├── Multi-AZ: Automatic failover
├── Encryption: At-rest + In-transit
├── Snapshot: 7 day retention
├── Security Group: 6379 from EKS Node SG only
└── Used For:
    ├── Event bus (Redis Streams)
    ├── Rate limiting (sliding window)
    ├── Cache (session data, query results)
    └── Application state
```

### 12.5 S3

| Bucket | Purpose | Features |
|--------|---------|----------|
| `chirp-prod-media` | Media files | Versioning, AES256, lifecycle (IA→Glacier), public blocked |
| `chirp-prod-frontend` | SPA hosting | Website config, CORS, public blocked, OAC for CloudFront |

### 12.6 CloudFront

```
Distribution: chirp-prod-frontend
├── Origin: S3 via Origin Access Control (sigv4)
├── Default Cache: GET/HEAD, TTL 86400s
├── Custom Error: 403/404 -> /index.html (SPA routing)
├── Price Class: PriceClass_100 (US, Canada, Europe)
└── SSL: ACM certificate (custom domain) or default
```

### 12.7 ECR

```
Repository: chirp-prod
├── Tags: IMMUTABLE
├── Scan on Push: Enabled
├── Lifecycle:
│   ├── Keep last 30 tagged images
│   └── Delete untagged after 7 days
└── Images: chirp-prod-{service}:latest
```

---

## 13. Kubernetes Architecture

### 13.1 Namespace

All resources in `chirp-prod` namespace.

### 13.2 ConfigMap

Shared configuration for all services:

```yaml
# Service discovery
AUTH_SERVICE_URL: http://auth-svc:8001
USER_SERVICE_URL: http://user-svc:8002
POST_SERVICE_URL: http://post-svc:8003
GRAPH_SERVICE_URL: http://graph-svc:8004
TIMELINE_SERVICE_URL: http://timeline-svc:8005
SEARCH_SERVICE_URL: http://search-svc:8006
NOTIFICATION_SERVICE_URL: http://notification-svc:8007
MESSAGING_SERVICE_URL: http://messaging-svc:8008
MEDIA_SERVICE_URL: http://media-svc:8009

# Event bus
EVENT_BUS_BACKEND: redis
EVENT_BUS_URL: redis://redis-svc:6379/1
EVENT_STREAM_PREFIX: chirp.events

# Auth
JWT_ALGORITHM: HS256
JWT_ACCESS_TOKEN_EXPIRY: 900
JWT_REFRESH_TOKEN_EXPIRY: 2592000

# CORS
CORS_ORIGINS: https://chirp.yourdomain.com
```

### 13.3 Secrets

```yaml
JWT_SECRET: <generated>
POSTGRES_PASSWORD: <generated>
DATABASE_URL_AUTH: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_auth
DATABASE_URL_USER: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_user
DATABASE_URL_POST: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_post
DATABASE_URL_GRAPH: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_graph
DATABASE_URL_TIMELINE: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_timeline
DATABASE_URL_SEARCH: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_search
DATABASE_URL_NOTIFICATION: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_notification
DATABASE_URL_MESSAGING: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_messaging
DATABASE_URL_MEDIA: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_media
DATABASE_URL_MODERATION: postgresql+asyncpg://chirp_admin:...@rds:5432/chirp_moderation
REDIS_URL: redis://redis-svc:6379/0
EVENT_BUS_URL: redis://redis-svc:6379/1
S3_BUCKET: chirp-prod-media
```

### 13.4 Deployments

Each API service has:
- **Deployment**: 2 replicas (default), rolling update
- **Service**: ClusterIP on its port
- **HPA**: 2-10 replicas, CPU 70%, Memory 80%
- **Init Container**: Alembic migration (for services with DB)
- **Liveness Probe**: `GET /health/live` (15s initial, 10s period)
- **Readiness Probe**: `GET /health/ready` (5s initial, 5s period)

Each worker has:
- **Deployment**: 2 replicas
- **No Service** (not exposed internally)
- **No HPA** (workers scale differently)
- **Same resource limits as parent service**

### 13.5 Resource Limits

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| Gateway | 250m | 1000m | 128Mi | 512Mi |
| Auth | 250m | 1000m | 128Mi | 512Mi |
| User | 100m | 500m | 64Mi | 256Mi |
| Post | 100m | 500m | 64Mi | 256Mi |
| Graph | 250m | 1000m | 128Mi | 512Mi |
| Timeline | 100m | 500m | 64Mi | 256Mi |
| Search | 100m | 500m | 64Mi | 256Mi |
| Notification | 100m | 500m | 64Mi | 256Mi |
| Messaging | 250m | 1000m | 128Mi | 512Mi |
| Media | 250m | 1000m | 128Mi | 512Mi |
| Moderation | 250m | 1000m | 128Mi | 512Mi |
| All Workers | (same as parent) | | | |

### 13.6 Ingress

Two ALB Ingress resources:

1. **gateway-ingress** (internet-facing)
   - Host: `*`
   - Path: `/*` -> gateway-svc:8000
   - SSL: HTTPS:443, redirect from HTTP
   - Health check: /health/live

2. **media-ingress** (internet-facing)
   - Host: `*`
   - Path: `/files/*` -> media-svc:8009
   - Path: `/api/v1/media/*` -> media-svc:8009
   - SSL: HTTPS:443, redirect from HTTP

3. **monitoring-ingress** (internal, VPC-only)
   - Host: `*`
   - Path: `/prometheus` -> prometheus-svc:9090
   - Path: `/grafana` -> grafana-svc:3000
   - Auth: IP restriction (10.0.0.0/8)

---

## 14. IAM Roles & Policies

### 14.1 GitHub Actions CI/CD Role

```
Role: chirp-prod-github-actions
Trust: OIDC federation (GitHub Actions, main branch only)
Policies:
├── chirp-ecr-push
│   ├── ecr:GetAuthorizationToken (all resources)
│   └── ecr:BatchCheckLayerAvailability, GetDownloadUrlForLayer,
│       BatchGetImage, PutImage, InitiateLayerUpload,
│       UploadLayerPart, CompleteLayerUpload (ECR repo only)
└── chirp-eks-access
    └── eks:DescribeCluster, eks:ListClusters (cluster ARN only)
```

### 14.2 Media Service IRSA Role

```
Role: chirp-prod-media
Trust: EKS OIDC (serviceaccount:chirp-prod:media)
Policy: chirp-media-s3
└── s3:PutObject, s3:GetObject, s3:DeleteObject, s3:ListBucket
    (media bucket + media/*)
```

### 14.3 EBS CSI Driver IRSA Role

```
Role: chirp-prod-ebs-csi
Trust: EKS OIDC (kube-system:ebs-csi-controller-sa)
Policy: AmazonEBS_CSI_Driver (AWS managed)
```

### 14.4 EKS Node Group Role

```
Role: chirp-prod-general-eks-node-group-*
Trust: ec2.amazonaws.com
Policies (AWS managed):
├── AmazonEKSWorkerNodePolicy
├── AmazonEKS_CNI_Policy
└── AmazonEC2ContainerRegistryReadOnly
```

### 14.5 EKS Cluster Role

```
Role: chirp-prod-cluster-*
Trust: eks.amazonaws.com
Policies (AWS managed):
├── AmazonEKSClusterPolicy
├── AmazonEKSVPCResourceController
└── chirp-prod-cluster-ClusterEncryption (KMS for secrets)
```

---

## 15. Networking & Security

### 15.1 Network Flow

```
Internet
   |
   v
CloudFront (HTTPS termination, caching)
   |
   v
ALB (HTTPS:443, SSL termination, WAF)
   |
   v
Public Subnets
   |
   v
NAT Gateway
   |
   v
Private Subnets
├── EKS Nodes (services run here)
│   ├── Gateway Pods -> Auth/User/Post/etc Pods (ClusterIP)
│   ├── Workers -> Redis Streams (ClusterIP)
│   └── All Pods -> RDS (private, SG-restricted)
├── RDS (private, SG: 5432 from EKS Node SG only)
└── ElastiCache (private, SG: 6379 from EKS Node SG only)
```

### 15.2 Security Groups

| Security Group | Inbound | Outbound |
|----------------|---------|----------|
| EKS Cluster | 443 from EKS Node SG | All |
| EKS Node | All from EKS Node SG, 443 from Cluster SG | All |
| RDS | 5432 from EKS Node SG | All |
| Redis | 6379 from EKS Node SG | All |

### 15.3 Encryption

| Component | At-Rest | In-Transit |
|-----------|---------|------------|
| RDS | Default (AES256) | SSL/TLS required |
| ElastiCache | Enabled | TLS (if password set) |
| S3 | AES256 (SSE-S3) | HTTPS |
| EBS | EBS encryption | N/A |
| Secrets | KMS (EKS envelope) | HTTPS |
| JWT | N/A | Bearer token |

---

## 16. Monitoring & Observability

### 16.1 Prometheus

- **Scrape interval**: 15s
- **Targets**: All pods via Kubernetes SD
- **Metrics**: `http_requests_total`, `http_request_duration_seconds`, `http_requests_in_flight`
- **Retention**: 30 days, 10GB max

### 16.2 Grafana

- **Datasource**: Prometheus (auto-provisioned)
- **Dashboard**: Chirp Overview
  - CPU usage by service
  - Memory usage by service
  - HTTP request rate
  - HTTP latency (p95)
  - Pod restarts
  - Active connections
  - Database connections
- **Access**: Internal ALB (VPC-only, IP restricted)

### 16.3 Health Checks

Every service exposes:
- `GET /health/live` — Process is running
- `GET /health/ready` — Can accept traffic (DB + Redis connected)

Gateway readiness checks all downstream services:
- **Critical**: auth, user, post, timeline (503 if down)
- **Non-critical**: search, notification, messaging, media, moderation (warning only)

---

## 17. CI/CD Pipeline

### 17.1 CI (ci.yml) — On PR

```
PR Created/Updated
   |
   v
Checkout code
   |
   v
Build all services (docker build)
   |
   v
Run tests per service (pytest)
   |
   v
Post test summary to PR
```

### 17.2 CD (cd.yml) — On Push to Main

```
Push to main
   |
   v
Build Docker images
   |
   v
Push to ECR (chirp-prod-{service}:latest)
   |
   v
Configure kubectl
   |
   v
Run migrations (kubectl apply job-migrate)
   |
   v
Wait for migration completion
   |
   v
Update deployments (kubectl set image)
   |
   v
Wait for rollout
```

---

## 18. Request Flow Diagrams

### 18.1 User Registration

```
Client -> Gateway -> Auth Service
   1. POST /api/v1/auth/register {email, username, password}
   2. Auth hashes password (Argon2id)
   3. Auth creates user in chirp_auth.users
   4. Auth publishes USER_REGISTERED event
   5. Auth returns JWT tokens
   |
   v (async)
User Worker consumes USER_REGISTERED
   6. Creates profile in chirp_user.users
   7. Initializes counters in chirp_user.user_counters
```

### 18.2 Create Post

```
Client -> Gateway -> Post Service
   1. POST /api/v1/posts {text, media_ids?}
   2. Post creates record in chirp_post.posts
   3. Post publishes POST_CREATED event
   4. Post returns post data
   |
   v (async, parallel)
Timeline Worker:
   5. Fetches followers from Graph Service
   6. Creates FeedEntry for each active follower
Search Worker:
   7. Indexes post text in chirp_search.post_search
   8. Updates hashtag counters
User Worker:
   9. Increments author's posts_count
```

### 18.3 Read Home Feed

```
Client -> Gateway -> Timeline + User + Post Services
   1. GET /api/v1/feed
   2. Gateway calls Timeline Service
   3. Timeline reads from feed_entries table
   4. Gateway calls User Service (batch)
   5. User Service returns author summaries
   6. Gateway calls Post Service (batch)
   7. Post Service returns full post data
   8. Gateway merges and returns hydrated feed
```

### 18.4 Search Posts

```
Client -> Gateway -> Search Service
   1. GET /api/v1/search?q=hello&sort=relevance
   2. Search executes PostgreSQL query:
      - FTS: plainto_tsquery + ts_rank
      - Trigram: similarity() > 0.2
      - Combined scoring: rank + sim * 0.5
   3. Search returns post_ids with scores
   4. Gateway hydrates via User + Post Services
```

### 18.5 Send Direct Message

```
Client -> Gateway -> Messaging + Graph Services
   1. POST /api/v1/messages/{user_id} {text}
   2. Messaging calls Graph Service
   3. Graph verifies follow relationship
   4. Messaging creates conversation (if new)
   5. Messaging creates message
   6. Messaging publishes MESSAGE_SENT event
   7. Messaging returns message data
   |
   v (async)
Notification Worker:
   8. Creates notification for recipient
```
