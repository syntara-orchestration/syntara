"""Unit tests for TFE error contract mapping."""

from http import HTTPStatus

from syntara.terraform.errors import TFEError, TFEErrorCode, map_http_status_to_error, redact_sensitive_content


def test_auth_failed() -> None:
    err = map_http_status_to_error(401, "unauthorized")
    assert err.error_code == TFEErrorCode.AUTH_FAILED
    assert not err.retryable


def test_authorization_failed() -> None:
    err = map_http_status_to_error(403, "forbidden")
    assert err.error_code == TFEErrorCode.AUTHORIZATION_FAILED
    assert not err.retryable


def test_tfe_rejected_bad_request() -> None:
    err = map_http_status_to_error(400, "bad request")
    assert err.error_code == TFEErrorCode.TFE_REJECTED
    assert not err.retryable


def test_tfe_rejected_unprocessable() -> None:
    err = map_http_status_to_error(422, "unprocessable")
    assert err.error_code == TFEErrorCode.TFE_REJECTED
    assert not err.retryable


def test_tfe_rejected_unmapped_client_error() -> None:
    err = map_http_status_to_error(418, "i am a teapot")
    assert err.error_code == TFEErrorCode.TFE_REJECTED
    assert not err.retryable


def test_not_found() -> None:
    err = map_http_status_to_error(404, "missing")
    assert err.error_code == TFEErrorCode.NOT_FOUND
    assert not err.retryable


def test_conflict() -> None:
    err = map_http_status_to_error(409, "conflict")
    assert err.error_code == TFEErrorCode.STATE_CONFLICT
    assert not err.retryable


def test_rate_limit_read_retryable() -> None:
    err = map_http_status_to_error(429, "slow down", mutating=False)
    assert err.error_code == TFEErrorCode.RATE_LIMITED
    assert err.retryable


def test_rate_limit_mutating_not_retryable() -> None:
    err = map_http_status_to_error(429, "slow down", mutating=True)
    assert err.error_code == TFEErrorCode.RATE_LIMITED
    assert not err.retryable


def test_transient_read_retryable() -> None:
    err = map_http_status_to_error(500, "server error", mutating=False)
    assert err.error_code == TFEErrorCode.TRANSIENT
    assert err.retryable


def test_transient_mutating_not_retryable() -> None:
    err = map_http_status_to_error(HTTPStatus.BAD_GATEWAY, "bad gateway", mutating=True)
    assert err.error_code == TFEErrorCode.TRANSIENT
    assert not err.retryable


def test_redact_sensitive_content_replaces_known_secret() -> None:
    secret = "my-long-api-token"  # noqa: S105
    text = f"request failed with header {secret} embedded"
    result = redact_sensitive_content(text, {secret})
    assert secret not in result
    assert "[REDACTED]" in result


def test_redact_sensitive_content_skips_short_secrets() -> None:
    short = "abc"
    text = f"value {short} here"
    assert redact_sensitive_content(text, {short}) == text


def test_redact_sensitive_content_bearer_pattern() -> None:
    text = "Auth was Bearer super-secret-token in logs"
    result = redact_sensitive_content(text)
    assert "super-secret-token" not in result
    assert "Bearer [REDACTED]" in result


def test_redact_sensitive_content_bearer_pattern_case_insensitive() -> None:
    text = "bearer tok12345 failed"
    result = redact_sensitive_content(text)
    assert "tok12345" not in result
    assert "[REDACTED]" in result
    assert result.startswith("Bearer ")


def test_redact_sensitive_content_authorization_header_pattern() -> None:
    text = "Header dump: Authorization: at-at-at-at-at"
    result = redact_sensitive_content(text)
    assert "at-at-at-at-at" not in result
    assert "Authorization: [REDACTED]" in result


def test_redact_sensitive_content_longer_secret_before_substring() -> None:
    long_secret = "abcdefghij"  # noqa: S105
    short_secret = "abcde"  # noqa: S105
    text = f"leaked {long_secret}"
    result = redact_sensitive_content(text, {short_secret, long_secret})
    assert long_secret not in result
    assert short_secret not in result
    assert result == "leaked [REDACTED]"


def test_redact_sensitive_content_empty_string() -> None:
    assert redact_sensitive_content("") == ""


def test_to_dict_includes_error_code() -> None:
    err = TFEError(
        "msg",
        error_code=TFEErrorCode.AUTH_FAILED,
        http_status=401,
        retryable=False,
    )
    payload = err.to_dict()
    assert payload["errorCode"] == "AUTH_FAILED"
    assert payload["message"] == "msg"
    assert payload["httpStatus"] == 401
    assert payload["retryable"] is False
