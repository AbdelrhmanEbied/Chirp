"""Tests for the chirp_common shared library."""

from __future__ import annotations

import pytest
from chirp_common.ids import new_ulid, ulid_timestamp_ms, is_ulid, ULID_LENGTH
from chirp_common.errors import (
    AppError, BadRequestError, ValidationError, UnauthorizedError,
    ForbiddenError, NotFoundError, ConflictError, RateLimitedError,
    DependencyError, ServiceUnavailableError,
)
from chirp_common.pagination import encode_cursor, decode_cursor, build_page, PageParams
from chirp_common.security import (
    hash_password, verify_password, needs_rehash,
    generate_opaque_token, hash_token,
)
from chirp_common.timeutil import utcnow, ensure_utc
from datetime import UTC, datetime


class TestULIDs:
    def test_new_ulid_length(self) -> None:
        assert len(new_ulid()) == ULID_LENGTH

    def test_new_ulid_is_valid(self) -> None:
        assert is_ulid(new_ulid())

    def test_ulid_timestamp(self) -> None:
        ulid = new_ulid()
        ts = ulid_timestamp_ms(ulid)
        assert ts > 0

    def test_is_ulid_rejects_invalid(self) -> None:
        assert not is_ulid("short")
        assert not is_ulid("x" * 30)
        assert not is_ulid("")


class TestErrors:
    def test_app_error_defaults(self) -> None:
        err = AppError()
        assert err.status_code == 500
        assert err.code == "internal_error"

    def test_not_found_error(self) -> None:
        err = NotFoundError("Not here")
        assert err.status_code == 404
        assert err.message == "Not here"
        assert err.code == "not_found"

    def test_conflict_error(self) -> None:
        err = ConflictError("Taken", code="taken")
        assert err.status_code == 409
        assert err.code == "taken"

    def test_unauthorized_error(self) -> None:
        err = UnauthorizedError("Nope")
        assert err.status_code == 401

    def test_forbidden_error(self) -> None:
        err = ForbiddenError("No access")
        assert err.status_code == 403

    def test_rate_limited_error(self) -> None:
        err = RateLimitedError(retry_after_seconds=60)
        assert err.status_code == 429
        assert err.retry_after_seconds == 60

    def test_dependency_error(self) -> None:
        err = DependencyError("Down")
        assert err.status_code == 502

    def test_error_to_payload(self) -> None:
        err = NotFoundError("missing")
        payload = err.to_payload(request_id="req-123")
        assert payload["error"]["code"] == "not_found"
        assert payload["error"]["request_id"] == "req-123"

    def test_error_with_details(self) -> None:
        err = ValidationError(details={"field": "name"})
        assert err.details == {"field": "name"}


class TestPagination:
    def test_encode_decode_cursor(self) -> None:
        cursor = encode_cursor("my-sort-key")
        decoded = decode_cursor(cursor)
        assert decoded == "my-sort-key"

    def test_decode_invalid_cursor_raises(self) -> None:
        with pytest.raises(Exception):
            decode_cursor("not-a-valid-cursor")

    def test_build_page(self) -> None:
        items = list(range(5))
        params = PageParams(limit=3)
        page = build_page(items, params, sort_key=lambda x: str(x))
        assert len(page.items) == 3
        assert page.page.has_more is True
        assert page.page.next_cursor is not None

    def test_build_page_no_more(self) -> None:
        items = list(range(2))
        params = PageParams(limit=5)
        page = build_page(items, params, sort_key=lambda x: str(x))
        assert len(page.items) == 2
        assert page.page.has_more is False
        assert page.page.next_cursor is None


class TestSecurity:
    def test_hash_and_verify_password(self) -> None:
        h = hash_password("my-secret-password")
        assert verify_password("my-secret-password", h)
        assert not verify_password("wrong-password", h)

    def test_generate_opaque_token(self) -> None:
        t1 = generate_opaque_token()
        t2 = generate_opaque_token()
        assert t1 != t2
        assert len(t1) > 20

    def test_hash_token(self) -> None:
        h = hash_token("my-refresh-token")
        assert len(h) == 64  # SHA-256 hex

    def test_needs_rehash(self) -> None:
        h = hash_password("test")
        assert not needs_rehash(h)


class TestTimeUtil:
    def test_utcnow(self) -> None:
        now = utcnow()
        assert now.tzinfo is not None

    def test_ensure_utc_naive(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0, 0)
        aware = ensure_utc(naive)
        assert aware.tzinfo == UTC

    def test_ensure_utc_aware(self) -> None:
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = ensure_utc(aware)
        assert result.tzinfo == UTC
