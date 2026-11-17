"""Unit tests for forms WorkflowApiClient."""

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import respx

from syntara.forms.clients.workflow_client import WorkflowApiClient


class TestWorkflowApiClient:
    """Test WorkflowApiClient functionality."""

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_form_signal_success(self) -> None:
        """Test successful form submission signal sending."""
        execution_id = uuid4()
        form_prompt_id = "form1"
        temporal_activity_id = "form1"
        form_response = {
            "outcome": "submitted",
            "response_data": {"email": "test@example.com", "name": "Test User"},
            "responded_by": "jsmith",
            "responded_at": "2026-09-21T10:00:00+00:00",
            "prompt_id": str(uuid4()),
        }

        with patch("syntara.core.utils.http_retry_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                # Mock successful HTTP response
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(return_value=httpx.Response(200))

                async with WorkflowApiClient() as client:
                    await client.send_form_signal(
                        execution_id=execution_id,
                        form_prompt_id=form_prompt_id,
                        form_response=form_response,
                        temporal_activity_id=temporal_activity_id,
                    )

                # Verify the signal URL was generated correctly
                mock_generate_url.assert_called_once_with(execution_id, temporal_activity_id)

                # Verify the HTTP request was made correctly
                assert signal_route.called
                request = signal_route.calls[0].request
                assert request.method == "POST"
                assert str(request.url) == "http://localhost:8000/api/v1/signal"
                assert request.headers["content-type"] == "application/json"

                # Verify the request payload
                request_json = json.loads(request.content)
                expected_payload = {
                    "signal_data": form_response,
                }
                assert request_json == expected_payload

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_form_signal_uses_temporal_activity_id(self) -> None:
        """Loop-body form prompts signal the Temporal activity ID."""
        execution_id = uuid4()
        form_prompt_id = "form1"
        temporal_activity_id = "form1_iter_0"
        form_response = {
            "outcome": "submitted",
            "response_data": {"field1": "value1"},
            "responded_by": "user",
            "responded_at": "2026-09-21T10:00:00+00:00",
            "prompt_id": str(uuid4()),
        }

        with patch("syntara.core.utils.http_retry_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                respx.post("http://localhost:8000/api/v1/signal").mock(return_value=httpx.Response(200))

                async with WorkflowApiClient() as client:
                    await client.send_form_signal(
                        execution_id=execution_id,
                        form_prompt_id=form_prompt_id,
                        form_response=form_response,
                        temporal_activity_id=temporal_activity_id,
                    )

                # Should use the loop iteration activity ID
                mock_generate_url.assert_called_once_with(execution_id, temporal_activity_id)

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_form_signal_success_after_retries(self) -> None:
        """Test successful form signal sending after retries."""
        execution_id = uuid4()
        form_prompt_id = "form1"
        form_response = {
            "outcome": "submitted",
            "response_data": {},
            "responded_by": "user",
            "responded_at": "2026-09-21T10:00:00+00:00",
            "prompt_id": str(uuid4()),
        }

        with patch("syntara.core.utils.http_retry_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                # First call fails with server error, second succeeds
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    side_effect=[
                        httpx.Response(500, text="Server Error"),
                        httpx.Response(200),
                    ]
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        await client.send_form_signal(
                            execution_id=execution_id,
                            form_prompt_id=form_prompt_id,
                            form_response=form_response,
                            temporal_activity_id=form_prompt_id,
                        )

                # Should have made 2 requests (1 failure + 1 success)
                assert len(signal_route.calls) == 2

                # Verify sleep was called for backoff
                mock_sleep.assert_called_once()

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_form_signal_failure_retries_exhausted(self) -> None:
        """Test form signal failure after exhausting retries."""
        execution_id = uuid4()
        form_prompt_id = "form1"
        form_response = {
            "outcome": "submitted",
            "response_data": {},
            "responded_by": "user",
            "responded_at": "2026-09-21T10:00:00+00:00",
            "prompt_id": str(uuid4()),
        }

        with patch("syntara.core.utils.http_retry_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    return_value=httpx.Response(500, text="Server Error")
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        with pytest.raises(httpx.HTTPStatusError, match="Server Error"):
                            await client.send_form_signal(
                                execution_id=execution_id,
                                form_prompt_id=form_prompt_id,
                                form_response=form_response,
                                temporal_activity_id=form_prompt_id,
                            )

                # Should have made max_retries + 1 requests (3 in fast settings)
                assert len(signal_route.calls) == 3

                # Should have slept max_retries times (2 times for fast settings)
                assert mock_sleep.call_count == 2

    async def test_send_form_signal_failure_no_retries(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        """Test form signal failure with max_retries=0."""
        execution_id = uuid4()
        form_prompt_id = "form1"
        form_response = {
            "outcome": "submitted",
            "response_data": {},
            "responded_by": "user",
            "responded_at": "2026-09-21T10:00:00+00:00",
            "prompt_id": str(uuid4()),
        }

        with (
            override_settings(workflow_client_max_retries=0),
            patch("syntara.core.utils.http_retry_client.generate_activity_signal_url") as mock_generate_url,
        ):
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    return_value=httpx.Response(500, text="Server Error")
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        with pytest.raises(httpx.HTTPStatusError, match="Server Error"):
                            await client.send_form_signal(
                                execution_id=execution_id,
                                form_prompt_id=form_prompt_id,
                                form_response=form_response,
                                temporal_activity_id=form_prompt_id,
                            )

                    # Should have made only 1 request (no retries)
                    assert len(signal_route.calls) == 1

                    # Should not have slept (no retries)
                    mock_sleep.assert_not_called()

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_form_signal_retries_on_connection_error(self) -> None:
        """Test form signal retries on connection errors."""
        execution_id = uuid4()
        form_prompt_id = "form1"
        form_response = {
            "outcome": "submitted",
            "response_data": {},
            "responded_by": "user",
            "responded_at": "2026-09-21T10:00:00+00:00",
            "prompt_id": str(uuid4()),
        }

        with patch("syntara.core.utils.http_retry_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                # First call fails with connection error, second succeeds
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    side_effect=[
                        httpx.ConnectError("Connection refused"),
                        httpx.Response(200),
                    ]
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        await client.send_form_signal(
                            execution_id=execution_id,
                            form_prompt_id=form_prompt_id,
                            form_response=form_response,
                            temporal_activity_id=form_prompt_id,
                        )

                # Should have made 2 requests
                assert len(signal_route.calls) == 2

                # Should have slept for backoff
                mock_sleep.assert_called_once()

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_form_signal_no_retry_on_4xx_error(self) -> None:
        """Test form signal does not retry on 4xx client errors."""
        execution_id = uuid4()
        form_prompt_id = "form1"
        form_response = {
            "outcome": "submitted",
            "response_data": {},
            "responded_by": "user",
            "responded_at": "2026-09-21T10:00:00+00:00",
            "prompt_id": str(uuid4()),
        }

        with patch("syntara.core.utils.http_retry_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    return_value=httpx.Response(404, text="Not Found")
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        with pytest.raises(httpx.HTTPStatusError, match="Not Found"):
                            await client.send_form_signal(
                                execution_id=execution_id,
                                form_prompt_id=form_prompt_id,
                                form_response=form_response,
                                temporal_activity_id=form_prompt_id,
                            )

                # Should have made only 1 request (no retries for 4xx)
                assert len(signal_route.calls) == 1

                # Should not have slept
                mock_sleep.assert_not_called()
