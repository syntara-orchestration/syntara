"""Tests for credential scrubber (T073)."""

from syntara.workflows.workflow_engine.utils.credential_scrubber import (
    REDACTED,
    scrub_credential_values,
    scrub_credentials,
)


class TestScrubCredentials:
    """Tests for scrub_credentials utility."""

    def test_scrubs_bearer_token(self) -> None:
        data = {"auth_type": "bearer", "bearer_token": "sk-secret-123"}
        result = scrub_credentials(data)
        assert result["bearer_token"] == REDACTED
        # auth_type is also scrubbed (derived from injector extra_vars)
        assert result["auth_type"] == REDACTED

    def test_scrubs_basic_auth(self) -> None:
        data = {"basic_username": "admin", "basic_password": "secret"}
        result = scrub_credentials(data)
        assert result["basic_username"] == REDACTED
        assert result["basic_password"] == REDACTED

    def test_scrubs_llm_keys(self) -> None:
        data = {"llm_api_key": "llm-key"}
        result = scrub_credentials(data)
        assert result["llm_api_key"] == REDACTED

    def test_scrubs_aap_credentials(self) -> None:
        data = {"aap_password": "pass", "aap_oauth_token": "token"}
        result = scrub_credentials(data)
        assert result["aap_password"] == REDACTED
        assert result["aap_oauth_token"] == REDACTED

    def test_scrubs_ssh_key(self) -> None:
        data = {"ssh_private_key": "-----BEGIN RSA PRIVATE KEY-----"}
        result = scrub_credentials(data)
        assert result["ssh_private_key"] == REDACTED

    def test_scrubs_secret_url(self) -> None:
        data = {"auth_type": "url", "secret_url": "https://hooks.slack.com/services/T/B/xxx"}
        result = scrub_credentials(data)
        assert result["secret_url"] == REDACTED
        assert result["auth_type"] == REDACTED

    def test_scrubs_resolved_credentials(self) -> None:
        data = {"_resolved_credentials": {"extra_vars": {"token": "secret"}}, "name": "test"}
        result = scrub_credentials(data)
        assert result["_resolved_credentials"] == REDACTED
        assert result["name"] == "test"

    def test_scrubs_nested_dict(self) -> None:
        data = {"outer": {"inner": {"bearer_token": "secret", "safe_key": "value"}}}
        result = scrub_credentials(data)
        assert result["outer"]["inner"]["bearer_token"] == REDACTED
        assert result["outer"]["inner"]["safe_key"] == "value"

    def test_preserves_non_credential_data(self) -> None:
        data = {"name": "test", "status": "active", "count": 42}
        result = scrub_credentials(data)
        assert result == data

    def test_handles_none(self) -> None:
        assert scrub_credentials(None) is None

    def test_handles_empty_dict(self) -> None:
        assert scrub_credentials({}) == {}

    def test_does_not_mutate_original(self) -> None:
        data = {"bearer_token": "secret", "name": "test"}
        scrub_credentials(data)
        assert data["bearer_token"] == "secret"  # noqa: S105

    def test_handles_list_with_dicts(self) -> None:
        data = [{"bearer_token": "a"}, {"name": "b"}]
        result = scrub_credentials(data)
        assert result[0]["bearer_token"] == REDACTED
        assert result[1]["name"] == "b"

    def test_scrubs_secret_values_key(self) -> None:
        data = {"_secret_values": ["token1", "token2"], "name": "test"}
        result = scrub_credentials(data)
        assert result["_secret_values"] == REDACTED
        assert result["name"] == "test"

    def test_scrubs_has_credentials_key(self) -> None:
        data = {"_has_credentials": True, "output": {"stdout": "hello"}}
        result = scrub_credentials(data)
        assert result["_has_credentials"] == REDACTED
        assert result["output"]["stdout"] == "hello"


class TestScrubCredentialValues:
    """Tests for value-based credential scrubbing."""

    def test_scrubs_secret_in_string(self) -> None:
        result = scrub_credential_values("output contains sk-secret-123 here", {"sk-secret-123"})
        assert result == f"output contains {REDACTED} here"

    def test_scrubs_secret_in_dict_values(self) -> None:
        data = {"stdout": "my token is sk-secret-123", "status": "ok"}
        result = scrub_credential_values(data, {"sk-secret-123"})
        assert f"my token is {REDACTED}" == result["stdout"]
        assert result["status"] == "ok"

    def test_scrubs_secret_in_nested_dict(self) -> None:
        data = {"output": {"body": {"data": "Bearer sk-secret-123"}}}
        result = scrub_credential_values(data, {"sk-secret-123"})
        assert result["output"]["body"]["data"] == f"Bearer {REDACTED}"

    def test_scrubs_secret_in_list(self) -> None:
        data = ["line1", "secret is sk-secret-123", "line3"]
        result = scrub_credential_values(data, {"sk-secret-123"})
        assert result[1] == f"secret is {REDACTED}"

    def test_scrubs_multiple_secrets(self) -> None:
        data = {"stdout": "user=admin pass=hunter2"}
        result = scrub_credential_values(data, {"admin", "hunter2"})
        assert "admin" not in result["stdout"]
        assert "hunter2" not in result["stdout"]

    def test_skips_short_values(self) -> None:
        """Values under 4 chars are skipped to avoid false positives."""
        data = {"stdout": "abc is common"}
        result = scrub_credential_values(data, {"abc"})
        assert result["stdout"] == "abc is common"

    def test_handles_empty_secret_values(self) -> None:
        data = {"stdout": "some output"}
        result = scrub_credential_values(data, set())
        assert result == data

    def test_handles_none(self) -> None:
        assert scrub_credential_values(None, {"secret"}) is None

    def test_preserves_non_string_values(self) -> None:
        data = {"count": 42, "flag": True}
        result = scrub_credential_values(data, {"secret"})
        assert result == data

    def test_does_not_mutate_original(self) -> None:
        data = {"stdout": "contains sk-secret-123"}
        scrub_credential_values(data, {"sk-secret-123"})
        assert "sk-secret-123" in data["stdout"]

    def test_script_stdout_scenario(self) -> None:
        """Simulates a script that echoes a credential value to stdout."""
        data = {
            "output": {
                "status": "completed",
                "return_code": 0,
                "stdout": "Connecting with token: eyJhbGciOiJSUzI1NiJ9.abc123\nDone.",
                "stderr": "",
            }
        }
        secret = "eyJhbGciOiJSUzI1NiJ9.abc123"  # noqa: S105
        result = scrub_credential_values(data, {secret})
        assert secret not in result["output"]["stdout"]
        assert REDACTED in result["output"]["stdout"]

    def test_http_response_echo_scenario(self) -> None:
        """Simulates an HTTP response that echoes the authorization header."""
        data = {
            "output": {
                "status_code": 200,
                "body": {"received_auth": "Bearer my-api-key-12345", "message": "ok"},
                "headers": {"content-type": "application/json"},
            }
        }
        result = scrub_credential_values(data, {"my-api-key-12345"})
        assert "my-api-key-12345" not in str(result)
        assert REDACTED in result["output"]["body"]["received_auth"]
