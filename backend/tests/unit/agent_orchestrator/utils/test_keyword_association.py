"""Tests for keyword-based tool relevance annotation (AAP-60442).

Tests cover:
- Keyword extraction (tokenization, stop word removal, normalization)
- Tool relevance scoring (keyword overlap)
- Tool annotation (hints prepended, all tools kept)
- Deterministic ordering (score descending, alphabetical tie-break)
- Edge cases (empty inputs, no matches, tools with no description)
"""

from unittest.mock import Mock

from langchain_core.tools import BaseTool

from syntara.agent_orchestrator.utils.keyword_association import (
    HINT_HIGH,
    HINT_LOW,
    annotate_tools_with_relevance,
    extract_keywords,
    score_tool_relevance,
)


def _make_tool(name: str, description: str = "") -> BaseTool:
    """Create a mock BaseTool with name and description."""
    tool = Mock(spec=BaseTool)
    tool.name = name
    tool.description = description
    return tool


class TestExtractKeywords:
    """Test keyword extraction from text."""

    def test_basic_extraction(self) -> None:
        keywords = extract_keywords("Search for server logs")
        assert "search" in keywords
        assert "server" in keywords
        assert "logs" in keywords

    def test_stop_words_removed(self) -> None:
        keywords = extract_keywords("the quick brown fox is very fast")
        assert "the" not in keywords
        assert "is" not in keywords
        assert "very" not in keywords
        assert "quick" in keywords
        assert "brown" in keywords
        assert "fox" in keywords
        assert "fast" in keywords

    def test_lowercased(self) -> None:
        keywords = extract_keywords("Search GITHUB Repository")
        assert "search" in keywords
        assert "github" in keywords
        assert "repository" in keywords

    def test_underscore_tokens_split(self) -> None:
        keywords = extract_keywords("file_search code_analysis")
        assert "file" in keywords
        assert "search" in keywords
        assert "code" in keywords
        assert "analysis" in keywords

    def test_empty_string(self) -> None:
        assert extract_keywords("") == set()

    def test_only_stop_words(self) -> None:
        keywords = extract_keywords("the is a an in on at to for of")
        assert keywords == set()

    def test_single_char_tokens_excluded(self) -> None:
        keywords = extract_keywords("a b c data x y z")
        assert "data" in keywords
        assert "a" not in keywords
        assert "b" not in keywords


class TestScoreToolRelevance:
    """Test relevance scoring between prompt keywords and tools."""

    def test_matching_keywords_score_positive(self) -> None:
        tool = _make_tool("search_repos", "Search GitHub repositories for code")
        prompt_keywords = extract_keywords("search github repos")
        score, matching = score_tool_relevance(prompt_keywords, tool)

        assert score > 0
        assert len(matching) > 0

    def test_no_match_scores_zero(self) -> None:
        tool = _make_tool("calculate_sum", "Add two numbers together")
        prompt_keywords = extract_keywords("search github repos")
        score, matching = score_tool_relevance(prompt_keywords, tool)

        assert score == 0.0
        assert matching == set()

    def test_partial_match(self) -> None:
        tool = _make_tool("file_read", "Read file contents from disk")
        prompt_keywords = extract_keywords("read the server configuration file")
        score, matching = score_tool_relevance(prompt_keywords, tool)

        assert 0 < score < 1.0
        assert "read" in matching or "file" in matching

    def test_empty_prompt_keywords(self) -> None:
        tool = _make_tool("search", "Search for things")
        score, matching = score_tool_relevance(set(), tool)

        assert score == 0.0
        assert matching == set()

    def test_tool_with_no_description(self) -> None:
        tool = _make_tool("search_repos", "")
        prompt_keywords = extract_keywords("search repos")
        score, matching = score_tool_relevance(prompt_keywords, tool)

        assert score > 0
        assert "search" in matching or "repos" in matching


def _has_any_hint(description: str) -> bool:
    """Check if description starts with any relevance hint."""
    return description.startswith((HINT_HIGH, HINT_LOW))


class TestAnnotateToolsWithRelevance:
    """Test the main annotation function."""

    def test_high_relevance_gets_high_hint(self) -> None:
        """Tools matching >= 50% of prompt keywords get HINT_HIGH."""
        tools = [
            _make_tool("analyze_logs", "Analyze server logs for errors and patterns"),
        ]
        result = annotate_tools_with_relevance("analyze server logs errors", tools)

        assert result[0].description.startswith(HINT_HIGH)

    def test_low_relevance_gets_low_hint(self) -> None:
        """Tools matching < 50% of prompt keywords get HINT_LOW."""
        tools = [
            _make_tool("search_repos", "Search GitHub repositories"),
        ]
        # "search" matches but "server", "logs", "errors", "analyze" don't → < 50%
        result = annotate_tools_with_relevance("search server logs errors analyze", tools)

        assert result[0].description.startswith(HINT_LOW)

    def test_irrelevant_tools_no_hint(self) -> None:
        tools = [
            _make_tool("search_repos", "Search GitHub repositories"),
            _make_tool("calculate_sum", "Add two numbers"),
        ]

        result = annotate_tools_with_relevance("search github repos", tools)

        calc_tool = next(t for t in result if t.name == "calculate_sum")
        assert not _has_any_hint(calc_tool.description)

    def test_tiered_hints_in_same_invocation(self) -> None:
        """High-scoring and low-scoring tools get different hints."""
        tools = [
            _make_tool("analyze_logs", "Analyze server logs for errors and patterns"),
            _make_tool("search_repos", "Search GitHub repositories"),
            _make_tool("calculate_sum", "Add two numbers"),
        ]

        result = annotate_tools_with_relevance("analyze server logs errors", tools)

        analyze_tool = next(t for t in result if t.name == "analyze_logs")
        search_tool = next(t for t in result if t.name == "search_repos")
        calc_tool = next(t for t in result if t.name == "calculate_sum")

        assert analyze_tool.description.startswith(HINT_HIGH)
        assert not _has_any_hint(calc_tool.description)
        # search_repos may or may not match depending on keywords — just verify it's not HINT_HIGH
        assert not search_tool.description.startswith(HINT_HIGH)

    def test_all_tools_returned(self) -> None:
        """No tools are removed — Aaron's requirement."""
        tools = [
            _make_tool("search_repos", "Search repositories"),
            _make_tool("calculate_sum", "Add numbers"),
            _make_tool("send_email", "Send an email"),
        ]

        result = annotate_tools_with_relevance("search repos", tools)

        assert len(result) == 3

    def test_sorted_by_score_descending(self) -> None:
        tools = [
            _make_tool("calculate_sum", "Add two numbers"),
            _make_tool("search_repos", "Search GitHub repositories for code"),
            _make_tool("send_email", "Send notification email"),
        ]

        result = annotate_tools_with_relevance("search github code", tools)

        assert result[0].name == "search_repos"

    def test_deterministic_alphabetical_tiebreak(self) -> None:
        """Equal-score tools sorted alphabetically by name."""
        tools = [
            _make_tool("zebra_search", "Search for data"),
            _make_tool("alpha_search", "Search for data"),
        ]

        result = annotate_tools_with_relevance("search data", tools)

        assert result[0].name == "alpha_search"
        assert result[1].name == "zebra_search"

    def test_empty_tools_list(self) -> None:
        result = annotate_tools_with_relevance("search repos", [])
        assert result == []

    def test_empty_prompt(self) -> None:
        tools = [_make_tool("search", "Search things")]
        result = annotate_tools_with_relevance("", tools)

        assert len(result) == 1
        assert not _has_any_hint(result[0].description)

    def test_prompt_with_only_stop_words(self) -> None:
        tools = [_make_tool("search", "Search things")]
        result = annotate_tools_with_relevance("the is a an", tools)

        assert len(result) == 1
        assert not _has_any_hint(result[0].description)

    def test_tool_with_empty_description(self) -> None:
        tools = [_make_tool("search_repos", "")]
        result = annotate_tools_with_relevance("search repos", tools)

        assert len(result) == 1
        assert _has_any_hint(result[0].description)

    def test_multiple_invocations_independent(self) -> None:
        """Each call annotates based on its own prompt."""
        tool1 = _make_tool("search", "Search for data")
        tool2 = _make_tool("search", "Search for data")

        annotate_tools_with_relevance("search data", [tool1])
        annotate_tools_with_relevance("calculate numbers", [tool2])

        assert _has_any_hint(tool1.description)
        assert not _has_any_hint(tool2.description)

    def test_no_double_annotation_in_loop(self) -> None:
        """Same tools annotated twice don't stack hints (LangGraph loop safety)."""
        tools = [_make_tool("search_repos", "Search GitHub repositories")]

        annotate_tools_with_relevance("search github repos", tools)
        first_desc = tools[0].description

        annotate_tools_with_relevance("search github repos", tools)
        second_desc = tools[0].description

        assert first_desc == second_desc
        assert second_desc.count(HINT_HIGH) <= 1
        assert second_desc.count(HINT_LOW) <= 1

    def test_hint_text_does_not_inflate_scores_in_loop(self) -> None:
        """Hint keywords like 'task' don't promote tools on re-annotation.

        Prompt containing 'task' would match hint text '[Relevant to this task]'
        if scoring reads the un-stripped description, inflating LOW → HIGH.
        """
        tools = [_make_tool("search_repos", "Search repositories")]

        result1 = annotate_tools_with_relevance("search repos task", tools)
        tier1 = result1[0].description

        result2 = annotate_tools_with_relevance("search repos task", tools)
        tier2 = result2[0].description

        assert tier1 == tier2

    def test_single_keyword_does_not_get_high_hint(self) -> None:
        """A single-keyword prompt cannot reach HINT_HIGH.

        Without a denominator floor, 'search' would score 1/1 = 100%
        for every tool containing 'search', making HINT_HIGH meaningless.
        The max(3, ...) floor caps it at ~33%, below HIGH_THRESHOLD.
        """
        tools = [
            _make_tool("search_repos", "Search GitHub repositories"),
            _make_tool("search_files", "Search files on disk"),
            _make_tool("calculate_sum", "Add two numbers"),
        ]

        result = annotate_tools_with_relevance("search", tools)

        search_tools = [t for t in result if "search" in t.name]
        for tool in search_tools:
            assert not tool.description.startswith(HINT_HIGH)
            assert tool.description.startswith(HINT_LOW)

    def test_two_keyword_prompt_capped_by_floor(self) -> None:
        """A 2-keyword prompt uses the floor denominator of 3."""
        tool = _make_tool("search_repos", "Search GitHub repositories")
        prompt_keywords = extract_keywords("search repos")
        score, _ = score_tool_relevance(prompt_keywords, tool)

        # 2 matches / max(3, 2) = 2/3 ≈ 0.67 → HINT_HIGH
        assert score == 2 / 3
