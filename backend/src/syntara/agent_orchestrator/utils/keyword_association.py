"""Keyword-based tool relevance annotation.

Matches user prompt keywords against tool names and descriptions to
annotate relevant tools with hints before passing them to the LLM.
All tools are kept — none are removed. The LLM naturally prefers
tools with relevance hints in their descriptions.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = structlog.stdlib.get_logger(__name__)

STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "need",
        "must",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "it",
        "they",
        "them",
        "their",
        "this",
        "that",
        "these",
        "those",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "into",
        "about",
        "between",
        "through",
        "during",
        "before",
        "after",
        "and",
        "or",
        "but",
        "not",
        "no",
        "if",
        "then",
        "else",
        "when",
        "what",
        "which",
        "who",
        "how",
        "where",
        "why",
        "all",
        "each",
        "every",
        "any",
        "some",
        "more",
        "most",
        "other",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        "only",
        "up",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "please",
        "help",
        "want",
        "like",
        "use",
        "using",
        "get",
    }
)

_WORD_PATTERN = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")

HINT_HIGH = "[Highly recommended for this task] "
HINT_LOW = "[Relevant to this task] "

HIGH_THRESHOLD = 0.5
LOW_THRESHOLD = 0.0
MIN_MATCHES_FOR_HIGH = 2


def extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text.

    Tokenizes, lowercases, removes stop words, and splits underscored
    compound tokens (e.g., "file_search" -> {"file", "search"}).
    """
    if not text:
        return set()

    tokens = _WORD_PATTERN.findall(text.lower())

    keywords: set[str] = set()
    for token in tokens:
        parts = token.split("_")
        for part in parts:
            if part and part not in STOP_WORDS and len(part) > 1:
                keywords.add(part)

    return keywords


def score_tool_relevance(
    prompt_keywords: set[str],
    tool: BaseTool,
) -> tuple[float, set[str]]:
    """Score how relevant a tool is to the prompt keywords.

    Returns (score, matching_keywords) where score is 0.0-1.0 based on
    the fraction of prompt keywords found in the tool's name + description.
    """
    if not prompt_keywords:
        return 0.0, set()

    tool_text = f"{tool.name} {tool.description or ''}"
    tool_keywords = extract_keywords(tool_text)

    if not tool_keywords:
        return 0.0, set()

    matching = prompt_keywords & tool_keywords
    score = len(matching) / max(3, len(prompt_keywords))

    return score, matching


def annotate_tools_with_relevance(
    prompt: str,
    tools: list[BaseTool],
) -> list[BaseTool]:
    """Annotate tools with keyword relevance hints and sort by relevance.

    Strips any existing hints before annotating to prevent stacking in
    LangGraph loops (GenericAgent → Tools → GenericAgent). Tools are sorted
    by relevance score (descending), then alphabetically by name for
    deterministic ordering. All tools are returned — none removed.
    """
    if not tools:
        return tools

    prompt_keywords = extract_keywords(prompt)
    if not prompt_keywords:
        logger.debug("No keywords extracted from prompt, skipping annotation", source="keyword_association")
        return tools

    scored: list[tuple[BaseTool, float, set[str]]] = []
    annotated_count = 0

    for tool in tools:
        # Strip any existing hints from previous loop iterations before scoring
        desc = tool.description or ""
        for hint in (HINT_HIGH, HINT_LOW):
            if desc.startswith(hint):
                desc = desc[len(hint) :]
                break
        tool.description = desc

        score, matching = score_tool_relevance(prompt_keywords, tool)

        if score >= HIGH_THRESHOLD and len(matching) >= MIN_MATCHES_FOR_HIGH:
            tool.description = f"{HINT_HIGH}{desc}"
            annotated_count += 1
        elif score > LOW_THRESHOLD:
            tool.description = f"{HINT_LOW}{desc}"
            annotated_count += 1
        else:
            tool.description = desc

        scored.append((tool, score, matching))

    scored.sort(key=lambda x: (-x[1], x[0].name))

    logger.info(
        "Tool relevance annotation complete",
        source="keyword_association",
        total_tools=len(tools),
        annotated_tools=annotated_count,
        prompt_keyword_count=len(prompt_keywords),
    )

    return [tool for tool, _, _ in scored]
