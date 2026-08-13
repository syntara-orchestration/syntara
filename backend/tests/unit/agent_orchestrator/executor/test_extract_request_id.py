"""Unit tests for _extract_request_id."""

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from syntara.agent_orchestrator.models.context_data import InvocationContextData
from syntara.agent_orchestrator.utils.context_helpers import extract_request_id


class TestExtractRequestId:
    """Tests for _extract_request_id helper."""

    def test_valid_uuid_in_metadata(self) -> None:
        uid = uuid4()
        ctx = InvocationContextData.model_validate({"metadata": {"request_id": str(uid)}})
        assert extract_request_id(ctx) == uid

    def test_missing_metadata_key(self) -> None:
        assert extract_request_id(InvocationContextData()) is None

    def test_metadata_not_a_dict(self) -> None:
        # When metadata is not a dict, model_validate raises ValidationError
        with pytest.raises(ValidationError, match="metadata must be a dict"):
            InvocationContextData.model_validate({"metadata": "not-a-dict"})

    def test_missing_request_id_in_metadata(self) -> None:
        ctx = InvocationContextData.model_validate({"metadata": {}})
        assert extract_request_id(ctx) is None

    def test_empty_string_request_id(self) -> None:
        ctx = InvocationContextData.model_validate({"metadata": {"request_id": ""}})
        assert extract_request_id(ctx) is None

    def test_invalid_uuid_string(self) -> None:
        ctx = InvocationContextData.model_validate({"metadata": {"request_id": "not-a-uuid"}})
        assert extract_request_id(ctx) is None

    def test_non_string_request_id(self) -> None:
        # Non-string request_id is rejected by Pydantic (str field, no coercion)
        with pytest.raises(ValidationError, match="Input should be a valid string"):
            InvocationContextData.model_validate({"metadata": {"request_id": 12345}})

    @pytest.mark.parametrize(
        "rid",
        [
            "550e8400-e29b-41d4-a716-446655440000",
            "550e8400e29b41d4a716446655440000",
        ],
        ids=["hyphenated", "compact"],
    )
    def test_uuid_formats(self, rid: str) -> None:
        ctx = InvocationContextData.model_validate({"metadata": {"request_id": rid}})
        result = extract_request_id(ctx)
        assert isinstance(result, UUID)
