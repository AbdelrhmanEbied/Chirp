"""Cursor (keyset) pagination.

Feeds, replies, followers and messages all use cursors rather than
`OFFSET`. Offset pagination degrades linearly -- `OFFSET 50000` makes
PostgreSQL walk and discard 50 000 rows -- and it skips or duplicates rows when
new items arrive while a client pages. Keyset pagination on a ULID primary key
is an index range scan whose cost does not depend on how deep you are.

Cursors are opaque to clients: base64 of `v1:<sort key>`. Encoding the version
means the sort key can change later without breaking clients that hold an old
cursor, since a stale cursor decodes to an error rather than to a wrong row.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Sequence
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from chirp_common.errors import BadRequestError

T = TypeVar("T")

CURSOR_VERSION = "v1"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def encode_cursor(sort_key: str) -> str:
    raw = f"{CURSOR_VERSION}:{sort_key}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> str:
    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + padding).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise BadRequestError("Malformed pagination cursor.", code="invalid_cursor") from exc
    version, _, sort_key = raw.partition(":")
    if version != CURSOR_VERSION or not sort_key:
        raise BadRequestError("Unsupported pagination cursor.", code="invalid_cursor")
    return sort_key


class PageParams(BaseModel):
    """Query parameters for a cursor-paginated endpoint."""

    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @property
    def after(self) -> str | None:
        """The decoded sort key to page from, if a cursor was supplied."""
        return decode_cursor(self.cursor) if self.cursor else None

    @property
    def fetch_limit(self) -> int:
        """Fetch one extra row to determine `has_more` without a COUNT."""
        return self.limit + 1


class PageInfo(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = DEFAULT_PAGE_SIZE


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: PageInfo


def build_page(
    rows: Sequence[T],
    params: PageParams,
    sort_key: Callable[[T], str],
) -> Page[T]:
    """Trim the extra row, derive `has_more` and emit the next cursor."""
    has_more = len(rows) > params.limit
    items = list(rows[: params.limit])
    next_cursor = encode_cursor(sort_key(items[-1])) if has_more and items else None
    return Page(
        items=items,
        page=PageInfo(next_cursor=next_cursor, has_more=has_more, limit=params.limit),
    )
