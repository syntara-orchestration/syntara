"""Unit tests for RelevancyConfiguration model.

This module tests the validation behavior and functionality of the RelevancyConfiguration
model, ensuring proper data validation and error handling.
"""

import pytest
from pydantic import ValidationError

from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)


class TestRelevancyConfigurationValidation:
    """Test validation rules for RelevancyConfiguration model."""

    def test_similarity_threshold_range_validation(self) -> None:
        """Test similarity_threshold must be between 0.0 and 1.0."""
        # Test threshold too low
        with pytest.raises(ValidationError) as exc_info:
            RelevancyConfiguration(
                checker_type="llm",
                similarity_threshold=-0.1,  # Invalid: below 0.0
                max_results=5,
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=0.1,
                mmr_settings={},
            )
        assert "similarity_threshold" in str(exc_info.value)

        # Test threshold too high
        with pytest.raises(ValidationError) as exc_info:
            RelevancyConfiguration(
                checker_type="llm",
                similarity_threshold=1.5,  # Invalid: above 1.0
                max_results=5,
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=0.1,
                mmr_settings={},
            )
        assert "similarity_threshold" in str(exc_info.value)

        # Test valid boundary values
        config_zero = RelevancyConfiguration(
            checker_type="llm",
            similarity_threshold=0.0,
            max_results=5,
            ranking_weights={},
            algorithm_parameters={},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )
        assert config_zero.similarity_threshold == pytest.approx(0.0)

        config_one = RelevancyConfiguration(
            checker_type="llm",
            similarity_threshold=1.0,
            max_results=5,
            ranking_weights={},
            algorithm_parameters={},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )
        assert config_one.similarity_threshold == pytest.approx(1.0)

    def test_max_results_validation(self) -> None:
        """Test max_results must be positive integer."""
        with pytest.raises(ValidationError) as exc_info:
            RelevancyConfiguration(
                checker_type="llm",
                similarity_threshold=0.5,
                max_results=0,  # Invalid: must be positive
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=0.1,
                mmr_settings={},
            )
        assert "max_results" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            RelevancyConfiguration(
                checker_type="llm",
                similarity_threshold=0.5,
                max_results=-5,  # Invalid: negative
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=0.1,
                mmr_settings={},
            )
        assert "max_results" in str(exc_info.value)

    def test_recency_weight_range_validation(self) -> None:
        """Test recency_weight must be between 0.0 and 1.0."""
        # Test weight too low
        with pytest.raises(ValidationError) as exc_info:
            RelevancyConfiguration(
                checker_type="llm",
                similarity_threshold=0.5,
                max_results=5,
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=-0.1,  # Invalid: below 0.0
                mmr_settings={},
            )
        assert "recency_weight" in str(exc_info.value)

        # Test weight too high
        with pytest.raises(ValidationError) as exc_info:
            RelevancyConfiguration(
                checker_type="llm",
                similarity_threshold=0.5,
                max_results=5,
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=1.5,  # Invalid: above 1.0
                mmr_settings={},
            )
        assert "recency_weight" in str(exc_info.value)
