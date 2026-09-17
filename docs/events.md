# Events

## The envelope

Every event, regardless of type or broker, carries the same metadata
(`chirp_common/events/envelope.py`):

| Field | Purpose |
|---|---|
| `id` | ULID. The deduplication key for idempotent consumers. |
| `type` | From the `EventType` enum. Determines the stream. |
| `version` | Payload schema version, so producers can evolve independently. |
| `producer` | Which service emitted it. |
| `subject_id` | The aggregate the event is about. |
| `actor_id` | The user who caused it, when there is one. |
| `occurred_at` | Lets consumers detect and discard out-of-order deliveries. |
| `correlation_id` | Ties the event to the originating user request. |
| `causation_id` | The request or event id that directly produced this one. |
| `payload` | The only type-specific part. |

`EventEnvelope.create` reads `correlation_id` and `causation_id` from the
ambient request context, so a log line in a worker three hops away carries the
same correlation id as the HTTP request that started it.

## Topology

One Redis stream per event type: `chirp.events.post.created`. One consumer
group per consuming service. One consumer name per process instance. Dead
letters go to `chirp.events.dlq`.

## Guarantees

- **At-least-once.** Consumers must be idempotent.
- **Ordering per stream only.** No ordering is guaranteed *across* types. A
  consumer that needs "the follow happened before the post" must not assume it.
- **Not transactional with the producer's database write.** See the outbox note
  in [decisions.md](decisions.md).

## Catalogue

| Event | Producer | Payload | Consumed by |
|---|---|---|---|
| `user.registered` | auth | `username`, `display_name` | (search, notification when built) |
| `user.profile_updated` | user | `username`, `display_name`, `avatar_media_id`, `changed_fields` | search, timeline cache invalidation |
| `user.deleted` | user | — | post, graph, search, timeline |
| `post.created` | post | `author_id`, `text`, `reply_to_id`, `hashtags`, `mentions` | timeline, search, **user** (posts_count) |
| `post.deleted` | post | `author_id` | timeline, search, **user** |
| `post.liked` / `post.unliked` | post | `post_id`, `author_id`, `actor_id` | notification |
| `post.reposted` / `post.unreposted` | post | `post_id`, `author_id` | timeline, notification |
| `post.reply_created` | post | `parent_id`, `parent_author_id` | notification |
| `post.quote_created` | post | `quoted_post_id`, `quoted_author_id` | notification |
| `post.user_mentioned` | post | `mentioned_user_ids` | notification |
| `graph.user_followed` / `graph.user_unfollowed` | graph | `follower_id`, `followee_id` | **user** (counters), timeline, notification |
| `graph.user_blocked` / `graph.user_unblocked` | graph | `blocker_id`, `blocked_id` | timeline, messaging |
| `messaging.message_sent` | messaging | `conversation_id`, `recipient_ids` | notification |
| `moderation.report_created` | moderation | `target_type`, `target_id` | moderation worker |
| `media.uploaded` / `media.deleted` | media | `media_id`, `owner_id` | post, user |

Rows in **bold** are implemented today. The rest are defined in the enum so
that producers and consumers agree on names before the services exist.

## Writing a consumer

```python
async def on_followed(event: EventEnvelope) -> None:
    async with context.database.session() as session:
        # The claim and the effect share one transaction.
        if not await claim_event(
            session, event_id=event.id, consumer=CONSUMER_GROUP,
            event_type=event.type.value,
        ):
            return                      # already applied
        await repository.adjust_counter(event.subject_id, "followers_count", 1)

worker.on(EventType.USER_FOLLOWED, on_followed)
```

Rules:

1. Claim inside the same transaction as your writes, or make the write
   naturally idempotent (an upsert keyed by the event's own identifiers) and
   say so in a comment.
2. Never assume ordering across event types.
3. Raise on failure — do not swallow. The worker's retry and dead-letter
   handling depends on the exception propagating.
4. Keep handlers short. A handler that takes seconds blocks its group.

## Failure handling

Handler raises → entry left unacknowledged → reclaimed after
`EVENT_CLAIM_IDLE_MS` → delivery count increments → at
`EVENT_MAX_DELIVERY_ATTEMPTS` the event goes to the DLQ stream and is
acknowledged so it stops blocking the group.

## Replacing the broker

Implement `chirp_common.events.bus.EventBus` and add a branch to
`build_event_bus`. Nothing in any service changes. For SQS/SNS the mapping is:
stream → topic+queue, consumer group → queue, `ack` → `DeleteMessage`,
`XAUTOCLAIM` → visibility timeout, DLQ stream → SQS redrive policy. Most of
the retry logic in `EventWorker` becomes the broker's job.
