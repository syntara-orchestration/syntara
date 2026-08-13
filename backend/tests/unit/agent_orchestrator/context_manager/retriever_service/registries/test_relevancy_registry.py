"""Unit tests for RelevancyRegistry class.

This module tests the functionality of RelevancyRegistry,
ensuring proper registration, retrieval, and error handling for relevancy checkers.
"""

import pytest

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import RegistryError
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.relevancy_checker import RelevancyChecker
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.agent_orchestrator.context_manager.retriever_service.registries.relevancy_registry import RelevancyRegistry


# Mock implementations for testing
class MockRelevancyChecker(RelevancyChecker):
    """Mock RelevancyChecker for testing."""

    async def check_relevancy(
        self,
        _document: RelevantDocument,
        _query: str,
        _config: RelevancyConfiguration,
        llm_credential_config: object = None,
    ) -> float:
        """Check document relevancy."""
        return 0.5


class TestRelevancyRegistry:
    """Test RelevancyRegistry functionality."""

    def test_create_empty_registry(self) -> None:
        """Test creating an empty RelevancyRegistry."""
        registry = RelevancyRegistry()
        assert registry.list_checkers() == []

    def test_register_checker_with_configuration(self) -> None:
        """Test registering a relevancy checker with configuration."""
        registry = RelevancyRegistry()
        config = RelevancyConfiguration(
            checker_type="mock",
            similarity_threshold=0.5,
            max_results=10,
            ranking_weights={},
            algorithm_parameters={},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )

        registry.register_checker("mock", MockRelevancyChecker, config)

        checkers = registry.list_checkers()
        assert "mock" in checkers
        assert len(checkers) == 1

    def test_get_checker(self) -> None:
        """Test retrieving a registered checker."""
        registry = RelevancyRegistry()
        config = RelevancyConfiguration(
            checker_type="mock",
            similarity_threshold=0.5,
            max_results=10,
            ranking_weights={},
            algorithm_parameters={},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )

        registry.register_checker("mock", MockRelevancyChecker, config)

        checker = registry.get_checker("mock")
        assert isinstance(checker, MockRelevancyChecker)

    def test_get_configuration(self) -> None:
        """Test retrieving a checker's configuration."""
        registry = RelevancyRegistry()
        config = RelevancyConfiguration(
            checker_type="mock",
            similarity_threshold=0.7,
            max_results=5,
            ranking_weights={"test": 0.5},
            algorithm_parameters={"param": "value"},
            grounding_parameters={},
            recency_weight=0.2,
            mmr_settings={},
        )

        registry.register_checker("mock", MockRelevancyChecker, config)

        retrieved_config = registry.get_configuration("mock")
        assert retrieved_config.checker_type == "mock"
        assert retrieved_config.similarity_threshold == pytest.approx(0.7)
        assert retrieved_config.max_results == 5
        assert retrieved_config.ranking_weights["test"] == pytest.approx(0.5)

    def test_get_unregistered_checker_raises_error(self) -> None:
        """Test getting unregistered checker raises RegistryError."""
        registry = RelevancyRegistry()

        with pytest.raises(RegistryError) as exc_info:
            registry.get_checker("nonexistent")
        assert "not registered" in str(exc_info.value).lower()

    def test_get_unregistered_configuration_raises_error(self) -> None:
        """Test getting unregistered configuration raises RegistryError."""
        registry = RelevancyRegistry()

        with pytest.raises(RegistryError) as exc_info:
            registry.get_configuration("nonexistent")
        assert "configuration for checker 'nonexistent' not found" in str(exc_info.value).lower()

    def test_register_duplicate_checker_raises_error(self) -> None:
        """Test registering duplicate checker name raises RegistryError."""
        registry = RelevancyRegistry()
        config = RelevancyConfiguration(
            checker_type="duplicate",
            similarity_threshold=0.5,
            max_results=10,
            ranking_weights={},
            algorithm_parameters={},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )

        registry.register_checker("duplicate", MockRelevancyChecker, config)

        with pytest.raises(RegistryError) as exc_info:
            registry.register_checker("duplicate", MockRelevancyChecker, config)
        assert "already registered" in str(exc_info.value).lower()

    def test_update_configuration(self) -> None:
        """Test updating an existing checker's configuration."""
        registry = RelevancyRegistry()
        original_config = RelevancyConfiguration(
            checker_type="mock",
            similarity_threshold=0.5,
            max_results=10,
            ranking_weights={},
            algorithm_parameters={},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )

        registry.register_checker("mock", MockRelevancyChecker, original_config)

        # Update configuration
        updated_config = RelevancyConfiguration(
            checker_type="mock",
            similarity_threshold=0.8,
            max_results=20,
            ranking_weights={"updated": 0.9},
            algorithm_parameters={"new_param": "new_value"},
            grounding_parameters={},
            recency_weight=0.3,
            mmr_settings={},
        )

        registry.update_configuration("mock", updated_config)

        retrieved_config = registry.get_configuration("mock")
        assert retrieved_config.similarity_threshold == pytest.approx(0.8)
        assert retrieved_config.max_results == 20
        assert retrieved_config.ranking_weights["updated"] == pytest.approx(0.9)

    def test_update_nonexistent_configuration_raises_error(self) -> None:
        """Test updating nonexistent configuration raises RegistryError."""
        registry = RelevancyRegistry()
        config = RelevancyConfiguration(
            checker_type="mock",
            similarity_threshold=0.5,
            max_results=10,
            ranking_weights={},
            algorithm_parameters={},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )

        with pytest.raises(RegistryError) as exc_info:
            registry.update_configuration("nonexistent", config)
        assert "not registered" in str(exc_info.value).lower()

    def test_register_multiple_checkers(self) -> None:
        """Test registering multiple checkers with different configurations."""
        registry = RelevancyRegistry()

        class AnotherMockChecker(RelevancyChecker):
            async def check_relevancy(
                self,
                _document: RelevantDocument,
                _query: str,
                _config: RelevancyConfiguration,
                llm_credential_config: object = None,
            ) -> float:
                return 0.8

        config1 = RelevancyConfiguration(
            checker_type="llm",
            similarity_threshold=0.7,
            max_results=15,
            ranking_weights={},
            algorithm_parameters={"model": "gpt-4"},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )

        config2 = RelevancyConfiguration(
            checker_type="keyword",
            similarity_threshold=0.3,
            max_results=5,
            ranking_weights={},
            algorithm_parameters={"case_sensitive": False},
            grounding_parameters={},
            recency_weight=0.05,
            mmr_settings={},
        )

        registry.register_checker("llm", MockRelevancyChecker, config1)
        registry.register_checker("keyword", AnotherMockChecker, config2)

        checkers = registry.list_checkers()
        assert set(checkers) == {"llm", "keyword"}

        # Both should be retrievable with correct configurations
        llm_checker = registry.get_checker("llm")
        keyword_checker = registry.get_checker("keyword")
        assert isinstance(llm_checker, MockRelevancyChecker)
        assert isinstance(keyword_checker, AnotherMockChecker)

        llm_config = registry.get_configuration("llm")
        keyword_config = registry.get_configuration("keyword")
        assert llm_config.similarity_threshold == pytest.approx(0.7)
        assert keyword_config.similarity_threshold == pytest.approx(0.3)
