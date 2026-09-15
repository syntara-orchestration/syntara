"""Unit tests for form exception classes.

Tests exception hierarchy, attributes, and message formatting.
"""

from datetime import UTC, datetime
from uuid import uuid4

from syntara.core.exceptions import SyntaraError
from syntara.forms.exceptions import (
    FormError,
    FormPromptAlreadyRequestedError,
    FormPromptAlreadyRespondedError,
    FormPromptCancelledError,
    FormPromptExpiredError,
    FormPromptNotFoundError,
)
from syntara.forms.models import FormPromptStatus


class TestFormExceptions:
    """Test form exception classes."""

    def test_form_error_base_class(self) -> None:
        """Test that FormError inherits from SyntaraError."""
        exc = FormError("Test error")
        assert isinstance(exc, SyntaraError)
        assert exc.message == "Test error"

    def test_form_prompt_not_found_error(self) -> None:
        """Test FormPromptNotFoundError attributes and message."""
        prompt_id = uuid4()
        exc = FormPromptNotFoundError(prompt_id)

        assert isinstance(exc, FormError)
        assert exc.form_prompt_id == prompt_id
        assert str(prompt_id) in exc.message
        assert "not found" in exc.message.lower()

    def test_form_prompt_already_responded_error(self) -> None:
        """Test FormPromptAlreadyRespondedError attributes and message."""
        prompt_id = uuid4()
        status = FormPromptStatus.SUBMITTED
        exc = FormPromptAlreadyRespondedError(prompt_id, status)

        assert isinstance(exc, FormError)
        assert exc.form_prompt_id == prompt_id
        assert exc.current_status == status
        assert str(prompt_id) in exc.message
        assert "submitted" in exc.message.lower()

    def test_form_prompt_expired_error_with_timeout(self) -> None:
        """Test FormPromptExpiredError with timeout_at."""
        prompt_id = uuid4()
        timeout_at = datetime.now(UTC)
        exc = FormPromptExpiredError(prompt_id, timeout_at)

        assert isinstance(exc, FormError)
        assert exc.form_prompt_id == prompt_id
        assert exc.timeout_at == timeout_at
        assert str(prompt_id) in exc.message
        assert "expired" in exc.message.lower()

    def test_form_prompt_expired_error_without_timeout(self) -> None:
        """Test FormPromptExpiredError without timeout_at."""
        prompt_id = uuid4()
        exc = FormPromptExpiredError(prompt_id)

        assert isinstance(exc, FormError)
        assert exc.form_prompt_id == prompt_id
        assert exc.timeout_at is None
        assert str(prompt_id) in exc.message

    def test_form_prompt_cancelled_error(self) -> None:
        """Test FormPromptCancelledError attributes and message."""
        prompt_id = uuid4()
        exc = FormPromptCancelledError(prompt_id)

        assert isinstance(exc, FormError)
        assert exc.form_prompt_id == prompt_id
        assert str(prompt_id) in exc.message
        assert "cancelled" in exc.message.lower()

    def test_form_prompt_already_requested_error_with_loop_path(self) -> None:
        """Test FormPromptAlreadyRequestedError with loop_iteration_path."""
        execution_id = uuid4()
        prompt_node_id = "test_node"
        loop_path = [0, 1, 2]
        exc = FormPromptAlreadyRequestedError(execution_id, prompt_node_id, loop_path)

        assert isinstance(exc, FormError)
        assert exc.execution_id == execution_id
        assert exc.prompt_node_id == prompt_node_id
        assert exc.loop_iteration_path == loop_path
        assert str(execution_id) in exc.message
        assert prompt_node_id in exc.message
        assert str(loop_path) in exc.message

    def test_form_prompt_already_requested_error_without_loop_path(self) -> None:
        """Test FormPromptAlreadyRequestedError without loop_iteration_path."""
        execution_id = uuid4()
        prompt_node_id = "test_node"
        exc = FormPromptAlreadyRequestedError(execution_id, prompt_node_id)

        assert isinstance(exc, FormError)
        assert exc.execution_id == execution_id
        assert exc.prompt_node_id == prompt_node_id
        assert exc.loop_iteration_path == []

    def test_form_prompt_already_requested_error_none_loop_path(self) -> None:
        """Test FormPromptAlreadyRequestedError with None loop_iteration_path."""
        execution_id = uuid4()
        prompt_node_id = "test_node"
        exc = FormPromptAlreadyRequestedError(execution_id, prompt_node_id, None)

        assert isinstance(exc, FormError)
        assert exc.loop_iteration_path == []
