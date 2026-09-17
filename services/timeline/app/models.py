"""Timeline service has no business tables of its own initially.

It assembles feeds by calling the graph and post services via HTTP.
Only the processed_events table is owned here for event consumption.
"""

from __future__ import annotations

from chirp_common.idempotency import ProcessedEvent  # noqa: F401 - registered on metadata
