"""Unit tests for ConfigurationManager implementation."""

import pytest

from syntara.agent_orchestrator.context_manager.retriever_service.config.configuration_manager import (
    ConfigurationManager,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)
from syntara.core.constants import RetrieverServiceDefaults


class TestConfigurationManager:
    """Test suite for ConfigurationManager."""

    @pytest.fixture
    def manager(self) -> ConfigurationManager:
        """Create ConfigurationManager instance."""
        return ConfigurationManager()

    def test_initialization(self, manager: ConfigurationManager) -> None:
        """Test ConfigurationManager initialization."""
        assert manager._default_llm_config is None
        assert manager._default_keyword_config is None
        assert manager._loaded is False

    def test_get_llm_configuration(self, manager: ConfigurationManager) -> None:
        """Test getting LLM configuration with real settings."""
        config = manager.get_llm_configuration()

        assert isinstance(config, RelevancyConfiguration)
        assert config.checker_type == "llm"
        assert config.similarity_threshold == pytest.approx(RetrieverServiceDefaults.LLM_SIMILARITY_THRESHOLD)
        assert config.max_results == RetrieverServiceDefaults.LLM_MAX_RESULTS
        assert config.algorithm_parameters["temperature"] == pytest.approx(RetrieverServiceDefaults.LLM_TEMPERATURE)
        assert config.algorithm_parameters["max_tokens"] == RetrieverServiceDefaults.LLM_MAX_TOKENS
        assert config.algorithm_parameters["system_prompt"] == RetrieverServiceDefaults.LLM_SYSTEM_PROMPT

        # Test ranking weights
        expected_weights = {
            "content_similarity": RetrieverServiceDefaults.LLM_RANKING_CONTENT_SIMILARITY,
            "file_metadata_relevance": RetrieverServiceDefaults.LLM_RANKING_FILE_METADATA_RELEVANCE,
            "recency": RetrieverServiceDefaults.LLM_RANKING_RECENCY,
        }
        for key, expected_value in expected_weights.items():
            assert config.ranking_weights[key] == pytest.approx(expected_value)

        # Test grounding parameters
        assert (
            config.grounding_parameters["include_file_metadata"] == RetrieverServiceDefaults.LLM_INCLUDE_FILE_METADATA
        )
        assert config.grounding_parameters["use_title_weighting"] == RetrieverServiceDefaults.LLM_USE_TITLE_WEIGHTING
        assert config.grounding_parameters["context_window_size"] == RetrieverServiceDefaults.CONTEXT_WINDOW_SIZE

        # Test MMR settings
        assert config.mmr_settings["lambda_param"] == pytest.approx(RetrieverServiceDefaults.LLM_MMR_LAMBDA_PARAM)
        assert config.mmr_settings["enable_mmr"] == RetrieverServiceDefaults.LLM_MMR_ENABLED

    def test_get_keyword_configuration(self, manager: ConfigurationManager) -> None:
        """Test getting keyword configuration with real settings."""
        config = manager.get_keyword_configuration()

        assert isinstance(config, RelevancyConfiguration)
        assert config.checker_type == "keyword"
        assert config.similarity_threshold == pytest.approx(RetrieverServiceDefaults.KEYWORD_SIMILARITY_THRESHOLD)
        assert config.max_results == RetrieverServiceDefaults.KEYWORD_MAX_RESULTS

        # Test algorithm parameters
        expected_algorithm_params = {
            "case_sensitive": RetrieverServiceDefaults.KEYWORD_CASE_SENSITIVE,
            "stem_words": RetrieverServiceDefaults.KEYWORD_STEM_WORDS,
            "remove_stopwords": RetrieverServiceDefaults.KEYWORD_REMOVE_STOPWORDS,
            "phrase_bonus_multiplier": RetrieverServiceDefaults.KEYWORD_PHRASE_BONUS_MULTIPLIER,
            "proximity_scoring": RetrieverServiceDefaults.KEYWORD_PROXIMITY_SCORING,
            "fuzzy_matching": RetrieverServiceDefaults.KEYWORD_FUZZY_MATCHING,
        }
        for key, expected_value in expected_algorithm_params.items():
            if isinstance(expected_value, float):
                assert config.algorithm_parameters[key] == pytest.approx(expected_value)

            if isinstance(expected_value, bool):
                assert config.algorithm_parameters[key] == expected_value

        # Test ranking weights (must sum to 1.0)
        expected_weights = {
            "term_frequency": RetrieverServiceDefaults.KEYWORD_RANKING_TERM_FREQUENCY,
            "filename_match": RetrieverServiceDefaults.KEYWORD_RANKING_FILENAME_MATCH,
            "content_density": RetrieverServiceDefaults.KEYWORD_RANKING_CONTENT_DENSITY,
            "proximity_bonus": RetrieverServiceDefaults.KEYWORD_RANKING_PROXIMITY_BONUS,
            "exact_match_bonus": RetrieverServiceDefaults.KEYWORD_RANKING_EXACT_MATCH_BONUS,
        }
        for key, expected_value in expected_weights.items():
            assert config.ranking_weights[key] == pytest.approx(expected_value)

        # Verify weights sum to 1.0
        total_weight = sum(config.ranking_weights.values())
        assert total_weight == pytest.approx(1.0)

        # Test grounding parameters
        expected_grounding_params = {
            "boost_title_matches": RetrieverServiceDefaults.KEYWORD_BOOST_TITLE_MATCHES,
            "boost_filename_matches": RetrieverServiceDefaults.KEYWORD_BOOST_FILENAME_MATCHES,
            "penalty_for_short_documents": RetrieverServiceDefaults.KEYWORD_PENALTY_FOR_SHORT_DOCUMENTS,
        }
        for key, expected_value in expected_grounding_params.items():
            assert config.grounding_parameters[key] == expected_value

        # Test MMR settings
        assert config.mmr_settings["lambda_param"] == pytest.approx(RetrieverServiceDefaults.KEYWORD_MMR_LAMBDA_PARAM)
        assert config.mmr_settings["enable_mmr"] == RetrieverServiceDefaults.KEYWORD_MMR_ENABLED

    def test_llm_configuration_has_all_required_settings(self, manager: ConfigurationManager) -> None:
        """Test that LLM configuration contains all settings required by LLMRelevancyChecker."""
        config = manager.get_llm_configuration()

        # All algorithm parameters required by LLMRelevancyChecker
        required_algorithm_params = ["temperature", "max_tokens", "system_prompt"]
        for param in required_algorithm_params:
            assert param in config.algorithm_parameters, f"Missing required algorithm parameter: {param}"
            assert config.algorithm_parameters[param] is not None, f"Algorithm parameter {param} is None"

        # All grounding parameters required by LLMRelevancyChecker
        required_grounding_params = ["include_file_metadata", "use_title_weighting", "context_window_size"]
        for param in required_grounding_params:
            assert param in config.grounding_parameters, f"Missing required grounding parameter: {param}"
            assert config.grounding_parameters[param] is not None, f"Grounding parameter {param} is None"

    def test_keyword_configuration_has_all_required_settings(self, manager: ConfigurationManager) -> None:
        """Test that keyword configuration contains all settings required by KeywordRelevancyChecker."""
        config = manager.get_keyword_configuration()

        # All algorithm parameters required by KeywordRelevancyChecker
        required_algorithm_params = [
            "case_sensitive",
            "stem_words",
            "remove_stopwords",
            "phrase_bonus_multiplier",
            "proximity_scoring",
        ]
        for param in required_algorithm_params:
            assert param in config.algorithm_parameters, f"Missing required algorithm parameter: {param}"
            assert config.algorithm_parameters[param] is not None, f"Algorithm parameter {param} is None"
