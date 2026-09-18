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

    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @property
    def after(self) -> str | None:
        return decode_cursor(self.cursor) if self.cursor else None

    @property
    def fetch_limit(self) -> int:
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
    has_more = len(rows) > params.limit
    items = list(rows[: params.limit])
    next_cursor = encode_cursor(sort_key(items[-1])) if has_more and items else None
    return Page(
        items=items,
        page=PageInfo(next_cursor=next_cursor, has_more=has_more, limit=params.limit),
    )
