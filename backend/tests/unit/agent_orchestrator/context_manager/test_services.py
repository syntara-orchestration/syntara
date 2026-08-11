"""Unit tests for Context Manager service components.

This module tests the individual service classes (CompressorService, AssemblerService) to ensure proper stub behavior.
"""

import math
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, Mock

import pytest

from syntara.agent_orchestrator.context_manager import (
    AssemblerService,
    CompressorService,
)
from tests.fixtures.settings import FakeSettingsCache


class TestCompressorService:
    """Tests for CompressorService behavior."""

    @pytest.fixture(autouse=True)
    def _mock_runtime_settings(  # type: ignore[misc]
        self, override_runtime_settings: Callable[..., AbstractContextManager[FakeSettingsCache]]
    ) -> None:
        """Auto-mock get_runtime_settings for compressor tests."""
        with override_runtime_settings():
            yield

    """Test the CompressorService stub implementation."""

    def test_compressor_initialization(self) -> None:
        """Test CompressorService initializes correctly."""
        mock_llm = AsyncMock()
        service = CompressorService(llm=mock_llm)
        assert service is not None

    async def test_compress_method_call(self) -> None:
        """Test compress method with valid string data."""
        # Mock dependencies to avoid actual LLM calls
        mock_token_calculator = Mock()
        mock_token_calculator.count_tokens.return_value = 50

        mock_llm = AsyncMock()
        service = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)
        test_docs = ["test document"]

        # Method should execute and return string content
        result = await service.compress(data=test_docs, max_tokens=100, strategy="greedy")
        assert isinstance(result, str)
        assert len(result) > 0


class TestAssemblerService:
    """Test the AssemblerService implementation."""

    def test_assembler_initialization(self) -> None:
        """Test AssemblerService initializes correctly with dependencies."""
        token_service = Mock()
        compressor_service = AsyncMock()
        service = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )
        assert service is not None
        assert service.token_service is token_service
        assert service.compressor_service is compressor_service

    @pytest.mark.asyncio
    async def test_assemble_method_with_empty_documents(self) -> None:
        """Test assemble method with empty documents returns valid ContextPackage."""
        token_service = Mock()
        compressor_service = AsyncMock()
        service = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Method should execute and return ContextPackage
        result = await service.assemble(
            documents=[],
            max_tokens=1000,
            compression_loop=0,
        )

        assert result is not None
        assert math.isclose(result.grounding_score, 0.0)

    @pytest.mark.asyncio
    async def test_assemble_with_null_documents(self) -> None:
        """Test assemble method with None documents."""
        token_service = Mock()
        compressor_service = AsyncMock()
        service = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Method should execute without raising exception
        result = await service.assemble(
            documents=None,
            max_tokens=1000,
            compression_loop=0,
        )

        assert result is not None
        assert math.isclose(result.grounding_score, 0.0)
