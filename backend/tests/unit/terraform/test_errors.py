"""Unit tests for TFE error contract mapping."""

from syntara.terraform.errors import TFEErrorCode, map_http_status_to_error


def test_auth_failed() -> None:
    err = map_http_status_to_error(401, "unauthorized")
    assert err.error_code == TFEErrorCode.AUTH_FAILED
    assert not err.retryable


def test_conflict() -> None:
    err = map_http_status_to_error(409, "conflict")
    assert err.error_code == TFEErrorCode.STATE_CONFLICT


def test_rate_limit_read_retryable() -> None:
    err = map_http_status_to_error(429, "slow down", mutating=False)
    assert err.error_code == TFEErrorCode.RATE_LIMITED
    assert err.retryable


def test_rate_limit_mutating_not_retryable() -> None:
    err = map_http_status_to_error(429, "slow down", mutating=True)
    assert err.error_code == TFEErrorCode.RATE_LIMITED
    assert not err.retryable
