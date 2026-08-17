"""Tests for callback_url stripping from externally-supplied context_data.

Verifies that the SSRF mitigation in the invocations router strips
internal-only fields (callback_url) from context_data when the request
does not come from a cert-authenticated internal service.
"""

from unittest.mock import AsyncMock, MagicMock

from syntara.invocations.router import _sanitize_context_data, create_invocation


def _make_request(*, is_cert_authenticated: bool) -> MagicMock:
    request = MagicMock()
    request.state.is_cert_authenticated = is_cert_authenticated
    return request


class TestSanitizeContextData:
    """Tests for _sanitize_context_data."""

    def test_strips_callback_url_from_external_request(self) -> None:
        context_data: dict[str, object] = {
            "callback_url": "https://evil.com/steal",
            "agent": "my-agent",
            "model": "gpt-4",
        }
        request = _make_request(is_cert_authenticated=False)

        result = _sanitize_context_data(context_data, request)

        assert "callback_url" not in result
        assert result["agent"] == "my-agent"
        assert result["model"] == "gpt-4"

    def test_preserves_callback_url_for_cert_authenticated_request(self) -> None:
        context_data: dict[str, object] = {
            "callback_url": "https://syntara:8000/api/v1/executions/abc/activities/step/signal",
            "agent": "my-agent",
        }
        request = _make_request(is_cert_authenticated=True)

        result = _sanitize_context_data(context_data, request)

        assert result["callback_url"] == context_data["callback_url"]
        assert result["agent"] == "my-agent"

    def test_no_op_when_no_internal_fields_present(self) -> None:
        context_data: dict[str, object] = {"agent": "my-agent", "model": "gpt-4"}
        request = _make_request(is_cert_authenticated=False)

        result = _sanitize_context_data(context_data, request)

        assert result == context_data

    def test_handles_missing_is_cert_authenticated(self) -> None:
        """Fail closed: if is_cert_authenticated is not set, treat as external."""
        context_data: dict[str, object] = {"callback_url": "https://evil.com"}
        request = MagicMock(spec=[])
        request.state = MagicMock(spec=[])

        result = _sanitize_context_data(context_data, request)

        assert "callback_url" not in result

    def test_does_not_mutate_original_dict(self) -> None:
        context_data: dict[str, object] = {"callback_url": "https://evil.com", "agent": "x"}
        request = _make_request(is_cert_authenticated=False)

        _sanitize_context_data(context_data, request)

        assert "callback_url" in context_data


class TestCreateInvocationSanitization:
    """Verify create_invocation strips callback_url for external callers."""

    async def test_callback_url_stripped_before_service_call(self) -> None:
        mock_service = AsyncMock()
        mock_service.create_invocation.return_value = MagicMock()

        mock_request = _make_request(is_cert_authenticated=False)

        mock_body = MagicMock()
        mock_body.prompt = "test"
        mock_body.session_id = "sess"
        mock_body.project_id = "00000000-0000-0000-0000-000000000000"
        mock_body.context_data = {
            "callback_url": "https://evil.com/publish",
            "agent": "my-agent",
        }

        await create_invocation(
            request=mock_request,
            request_body=mock_body,
            service=mock_service,
        )

        call_kwargs = mock_service.create_invocation.call_args
        passed_context = call_kwargs.kwargs.get("context_data") or call_kwargs[1].get("context_data")
        assert "callback_url" not in passed_context
        assert passed_context["agent"] == "my-agent"

    async def test_callback_url_preserved_for_cert_authenticated(self) -> None:
        mock_service = AsyncMock()
        mock_service.create_invocation.return_value = MagicMock()

        mock_request = _make_request(is_cert_authenticated=True)

        mock_body = MagicMock()
        mock_body.prompt = "test"
        mock_body.session_id = "sess"
        mock_body.project_id = "00000000-0000-0000-0000-000000000000"
        mock_body.context_data = {
            "callback_url": "https://syntara:8000/api/v1/executions/abc/activities/step/signal",
            "agent": "my-agent",
        }

        await create_invocation(
            request=mock_request,
            request_body=mock_body,
            service=mock_service,
        )

        call_kwargs = mock_service.create_invocation.call_args
        passed_context = call_kwargs.kwargs.get("context_data") or call_kwargs[1].get("context_data")
        assert passed_context["callback_url"] == mock_body.context_data["callback_url"]
