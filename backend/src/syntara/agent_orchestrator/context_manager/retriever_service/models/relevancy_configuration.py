"""RelevancyConfiguration model for configuring relevancy checker parameters.

This module provides the RelevancyConfiguration data model used for configuring
relevancy checking algorithms with tunable parameters.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from syntara.core.exceptions import SafeValueError


class RelevancyConfiguration(BaseModel):
    """Configuration container for relevancy checker tuning parameters.

    This model defines configuration parameters for different relevancy checking
    algorithms, allowing fine-tuning of behavior without code changes.

    Uses Pydantic BaseModel (not SQLModel) since:
    - Configuration is loaded from settings (not database table)
    - Managed through src/syntara/core/base.py patterns
    - Used for algorithm parameter passing, not API schemas

    Attributes:
        checker_type: Type of relevancy checker ("llm", "keyword", "semantic")
        similarity_threshold: Minimum relevancy score threshold (0.0 to 1.0)
        max_results: Maximum number of documents to return (positive integer)
        ranking_weights: Weights for different ranking factors
        algorithm_parameters: Algorithm-specific parameters (Top-k, Top-p, etc.)
        grounding_parameters: Reference relevance parameters
        recency_weight: Weight given to document recency (0.0 to 1.0)
        mmr_settings: Maximal marginal relevance configuration

    """

    checker_type: str = Field(..., description="Type of relevancy checker", min_length=1)
    similarity_threshold: float = Field(..., description="Minimum relevancy score threshold", ge=0.0, le=1.0)
    max_results: int = Field(..., description="Maximum number of documents to return", gt=0)
    ranking_weights: dict[str, float] = Field(default_factory=dict, description="Weights for different ranking factors")
    algorithm_parameters: dict[str, Any] = Field(default_factory=dict, description="Algorithm-specific parameters")
    grounding_parameters: dict[str, Any] = Field(default_factory=dict, description="Reference relevance parameters")
    recency_weight: float = Field(..., description="Weight given to document recency", ge=0.0, le=1.0)
    mmr_settings: dict[str, Any] = Field(default_factory=dict, description="Maximal marginal relevance configuration")

    @field_validator("ranking_weights")
    @classmethod
    def ranking_weights_sum_must_be_valid(cls, v: dict[str, float]) -> dict[str, float]:
        """Validate that ranking weights sum is within acceptable range."""
        if v:
            weights_sum = sum(v.values())
            min_weights_sum = 0.0
            max_weights_sum = 2.0
            if weights_sum <= min_weights_sum or weights_sum > max_weights_sum:
                error_msg = (
                    f"Ranking weights sum should be between {min_weights_sum} and {max_weights_sum}, got {weights_sum}"
                )
                raise SafeValueError(error_msg)
        return v

    @field_validator("mmr_settings")
    @classmethod
    def mmr_settings_lambda_param_must_be_valid(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate MMR settings parameters."""
        if v.get("enable_mmr", False):
            lambda_param = v.get("lambda_param", 0.5)
            if not isinstance(lambda_param, int | float) or not (0.0 <= lambda_param <= 1.0):
                error_msg = f"MMR lambda_param must be between 0.0 and 1.0, got {lambda_param}"
                raise SafeValueError(error_msg)
        return v
