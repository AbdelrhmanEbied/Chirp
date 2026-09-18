from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

http_requests_total = Counter(
    "chirp_http_requests_total",
    "HTTP requests handled.",
    ("service", "method", "path", "status"),
    registry=REGISTRY,
)
http_request_duration_seconds = Histogram(
    "chirp_http_request_duration_seconds",
    "HTTP request latency.",
    ("service", "method", "path"),
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)
http_requests_in_flight = Gauge(
    "chirp_http_requests_in_flight",
    "HTTP requests currently being handled.",
    ("service",),
    registry=REGISTRY,
)
db_query_duration_seconds = Histogram(
    "chirp_db_query_duration_seconds",
    "Database operation latency.",
    ("service", "operation"),
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)
cache_operations_total = Counter(
    "chirp_cache_operations_total",
    "Cache lookups by result.",
    ("service", "cache", "result"),
    registry=REGISTRY,
)
events_published_total = Counter(
    "chirp_events_published_total",
    "Events published to the bus.",
    ("service", "event_type"),
    registry=REGISTRY,
)
events_consumed_total = Counter(
    "chirp_events_consumed_total",
    "Events consumed, by outcome.",
    ("service", "event_type", "outcome"),
    registry=REGISTRY,
)
event_processing_duration_seconds = Histogram(
    "chirp_event_processing_duration_seconds",
    "Event handler latency.",
    ("service", "event_type"),
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)
event_queue_depth = Gauge(
    "chirp_event_queue_depth",
    "Pending entries in a consumer group.",
    ("service", "stream", "group"),
    registry=REGISTRY,
)
dependency_requests_total = Counter(
    "chirp_dependency_requests_total",
    "Outbound calls to sibling services.",
    ("service", "dependency", "outcome"),
    registry=REGISTRY,
)

@contextmanager
def observe_db(service: str, operation: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        db_query_duration_seconds.labels(service, operation).observe(
            time.perf_counter() - start
        )
