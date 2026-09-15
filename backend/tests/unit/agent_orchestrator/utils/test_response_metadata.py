"""Unit tests for LLM response_metadata chunk-merge normalization."""

from syntara.agent_orchestrator.utils.response_metadata import (
    collapse_concatenated_scalar,
    normalize_response_metadata,
)


class TestCollapseConcatenatedScalar:
    """collapse_concatenated_scalar undoes LangChain string-merge concatenation."""

    def test_finish_reason_stopstop(self) -> None:
        assert collapse_concatenated_scalar("stopstop") == "stop"

    def test_model_name_doubled(self) -> None:
        doubled = "openai/gpt-3.5-turboopenai/gpt-3.5-turbo"
        assert collapse_concatenated_scalar(doubled) == "openai/gpt-3.5-turbo"

    def test_already_correct_unchanged(self) -> None:
        assert collapse_concatenated_scalar("stop") == "stop"

    def test_odd_length_unchanged(self) -> None:
        assert collapse_concatenated_scalar("abc") == "abc"

    def test_even_length_not_repeated_unchanged(self) -> None:
        assert collapse_concatenated_scalar("length") == "length"

    def test_empty_string(self) -> None:
        assert collapse_concatenated_scalar("") == ""

    def test_quadrupled_collapses_to_single(self) -> None:
        assert collapse_concatenated_scalar("stopstopstopstop") == "stop"

    def test_tripled_collapses_to_single(self) -> None:
        assert collapse_concatenated_scalar("stop" * 3) == "stop"


class TestNormalizeResponseMetadata:
    """normalize_response_metadata copies and collapses known concatenated keys."""

    def test_collapses_finish_reason_and_model_name(self) -> None:
        normalized = normalize_response_metadata(
            {
                "finish_reason": "stopstop",
                "model_name": "openai/gpt-3.5-turboopenai/gpt-3.5-turbo",
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 4},
            }
        )
        assert normalized["finish_reason"] == "stop"
        assert normalized["model_name"] == "openai/gpt-3.5-turbo"
        assert normalized["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 4}

    def test_collapses_tripled_allowlisted_scalars(self) -> None:
        normalized = normalize_response_metadata(
            {
                "finish_reason": "stop" * 3,
                "service_tier": "default" * 3,
                "ls_provider": "openai" * 3,
            }
        )
        assert normalized["finish_reason"] == "stop"
        assert normalized["service_tier"] == "default"
        assert normalized["ls_provider"] == "openai"

    def test_does_not_collapse_unknown_string_keys(self) -> None:
        normalized = normalize_response_metadata({"note": "abab"})
        assert normalized["note"] == "abab"

    def test_does_not_mutate_input(self) -> None:
        original = {"finish_reason": "stopstop"}
        normalize_response_metadata(original)
        assert original["finish_reason"] == "stopstop"

    def test_none_and_empty(self) -> None:
        assert normalize_response_metadata(None) == {}
        assert normalize_response_metadata({}) == {}

    def test_non_string_values_copied(self) -> None:
        normalized = normalize_response_metadata({"logprobs": None, "n": 1})
        assert normalized["logprobs"] is None
        assert normalized["n"] == 1

    def test_rebuilds_token_usage_from_usage_metadata(self) -> None:
        normalized = normalize_response_metadata(
            {
                "finish_reason": "stopstop",
                "token_usage": {"prompt_tokens": 24, "completion_tokens": 16, "total_tokens": 40},
            },
            usage_metadata={"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
        )
        assert normalized["finish_reason"] == "stop"
        assert normalized["token_usage"] == {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
        }

    def test_usage_metadata_without_response_metadata(self) -> None:
        normalized = normalize_response_metadata(
            None,
            usage_metadata={"input_tokens": 5, "output_tokens": 2},
        )
        assert normalized["token_usage"] == {
            "prompt_tokens": 5,
            "completion_tokens": 2,
            "total_tokens": 7,
        }
