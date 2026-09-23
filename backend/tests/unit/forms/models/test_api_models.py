"""Tests for form request and response API models."""

import pytest
from pydantic import ValidationError

from syntara.forms.models.api_models import FormPromptSubmitRequest


class TestFormPromptSubmitRequest:
    """Tests for the user-facing form response request body."""

    def test_accepts_response_data(self) -> None:
        request = FormPromptSubmitRequest(response_data={"name": "Ada"})

        assert request.response_data == {"name": "Ada"}

    def test_requires_response_data(self) -> None:
        with pytest.raises(ValidationError):
            FormPromptSubmitRequest.model_validate({})

    def test_accepts_empty_response_data_for_service_validation(self) -> None:
        request = FormPromptSubmitRequest(response_data={})

        assert request.response_data == {}
