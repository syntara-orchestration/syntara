"""Global configuration manager for RetrieverService framework.

This module provides centralized configuration management for the RetrieverService
framework, integrating with the existing Nexus configuration patterns.
"""

import structlog

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import ConfigurationError
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)
from syntara.core.config.base import get_settings

logger = structlog.stdlib.get_logger(__name__)


class ConfigurationManager:
    """Global configuration manager for RetrieverService framework.

    This class manages configuration settings for the RetrieverService framework,
    providing centralized access to default configuration values loaded from
    application settings.

    The manager integrates with existing Nexus configuration patterns and
    provides type-safe access to configuration settings.

    Example Usage:
        ```python
        manager = ConfigurationManager()

        # Get default configurations
        llm_config = manager.get_llm_configuration()
        keyword_config = manager.get_keyword_configuration()
        ```
    """

    def __init__(self) -> None:
        """Initialize configuration manager with default settings."""
        self._default_llm_config: RelevancyConfiguration | None = None
        self._default_keyword_config: RelevancyConfiguration | None = None
        self._loaded = False
        logger.debug("Initialized ConfigurationManager")

    def _load_default_configurations(self) -> None:
        """Load default configurations for built-in checker types from settings."""
        if self._loaded:
            return

        # Get settings from the main configuration
        settings = get_settings()

        # LLM configuration using settings
        self._default_llm_config = RelevancyConfiguration(
            checker_type="llm",
            similarity_threshold=settings.retriever_llm_similarity_threshold,
            max_results=settings.retriever_llm_max_results,
            ranking_weights={
                "content_similarity": settings.retriever_llm_ranking_content_similarity,
                "file_metadata_relevance": settings.retriever_llm_ranking_file_metadata_relevance,
                "recency": settings.retriever_llm_ranking_recency,
            },
            algorithm_parameters={
                "temperature": settings.retriever_llm_temperature,
                "max_tokens": settings.retriever_llm_max_tokens,
                "system_prompt": settings.retriever_llm_system_prompt,
            },
            grounding_parameters={
                "include_file_metadata": settings.retriever_llm_include_file_metadata,
                "context_window_size": settings.retriever_context_window_size,
                "use_title_weighting": settings.retriever_llm_use_title_weighting,
            },
            recency_weight=settings.retriever_llm_recency_weight,
            mmr_settings={
                "lambda_param": settings.retriever_llm_mmr_lambda_param,
                "enable_mmr": settings.retriever_llm_mmr_enabled,
            },
        )

        # Keyword configuration using settings
        self._default_keyword_config = RelevancyConfiguration(
            checker_type="keyword",
            similarity_threshold=settings.retriever_keyword_similarity_threshold,
            max_results=settings.retriever_keyword_max_results,
            ranking_weights={
                "term_frequency": settings.retriever_keyword_ranking_term_frequency,
                "filename_match": settings.retriever_keyword_ranking_filename_match,
                "content_density": settings.retriever_keyword_ranking_content_density,
                "proximity_bonus": settings.retriever_keyword_ranking_proximity_bonus,
                "exact_match_bonus": settings.retriever_keyword_ranking_exact_match_bonus,
                "fuzzy_match_bonus": settings.retriever_keyword_ranking_fuzzy_match_bonus,
            },
            algorithm_parameters={
                "case_sensitive": settings.retriever_keyword_case_sensitive,
                "stem_words": settings.retriever_keyword_stem_words,
                "remove_stopwords": settings.retriever_keyword_remove_stopwords,
                "phrase_bonus_multiplier": settings.retriever_keyword_phrase_bonus_multiplier,
                "proximity_scoring": settings.retriever_keyword_proximity_scoring,
                "fuzzy_matching": settings.retriever_keyword_fuzzy_matching,
            },
            grounding_parameters={
                "boost_title_matches": settings.retriever_keyword_boost_title_matches,
                "boost_filename_matches": settings.retriever_keyword_boost_filename_matches,
                "penalty_for_short_documents": settings.retriever_keyword_penalty_for_short_documents,
            },
            recency_weight=settings.retriever_keyword_recency_weight,
            mmr_settings={
                "lambda_param": settings.retriever_keyword_mmr_lambda_param,
                "enable_mmr": settings.retriever_keyword_mmr_enabled,
            },
        )

        self._loaded = True
        logger.info(
            "Loaded configurations from settings",
            llm_threshold=settings.retriever_llm_similarity_threshold,
            keyword_threshold=settings.retriever_keyword_similarity_threshold,
        )

    def get_llm_configuration(self) -> RelevancyConfiguration:
        """Get default configuration for LLM relevancy checking.

        Returns:
            Default RelevancyConfiguration for LLM checker

        """
        self._load_default_configurations()
        if self._default_llm_config is None:
            error_msg = "LLM configuration not available"
            raise ConfigurationError(error_msg)
        return self._default_llm_config

    def get_keyword_configuration(self) -> RelevancyConfiguration:
        """Get default configuration for keyword relevancy checking.

        Returns:
            Default RelevancyConfiguration for keyword checker

        """
        self._load_default_configurations()
        if self._default_keyword_config is None:
            error_msg = "Keyword configuration not available"
            raise ConfigurationError(error_msg)
        return self._default_keyword_config
