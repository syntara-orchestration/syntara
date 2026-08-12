"""Keyword-based relevancy checker implementation.

This module provides a keyword-based relevancy checker that scores documents
based on keyword matching with configurable algorithms and weighting.
"""

from __future__ import annotations

from collections import Counter
from math import log
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
        RelevancyConfiguration,
    )
    from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
    from syntara.agent_orchestrator.models.llm_credential_config import LLMCredentialConfig

import structlog
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from spacy.lang.en import English
from spacy.lang.en.stop_words import STOP_WORDS

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import RelevancyCheckError
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.relevancy_checker import RelevancyChecker
from syntara.core.constants import RetrieverServiceDefaults

logger = structlog.stdlib.get_logger(__name__)


class KeywordRelevancyChecker(RelevancyChecker):
    """Keyword-based relevancy checker with configurable scoring algorithms.

    This implementation scores document relevancy based on keyword matching
    with support for various text processing options and scoring mechanisms:

    - Term frequency analysis
    - Filename and metadata matching
    - Phrase detection with bonus scoring
    - Proximity-based scoring
    - Case sensitivity options
    - Word stemming and stopword removal

    The checker is designed as a reliable fallback for LLM-based checking
    and provides fast, deterministic scoring based on text analysis.

    Scoring Components:
    1. Content TF-IDF scoring
    2. Filename matching bonus
    3. Phrase matching bonus
    4. Proximity scoring (nearby terms)
    5. Exact match bonus
    6. Document length normalization

    Example Usage:
        ```python
        checker = KeywordRelevancyChecker()
        config = RelevancyConfiguration(
            checker_type="keyword",
            algorithm_parameters={
                "case_sensitive": False,
                "stem_words": True,
                "phrase_bonus_multiplier": 1.5
            }
        )

        score = await checker.check_relevancy(document, "machine learning", config)
        ```
    """

    def __init__(self) -> None:
        """Initialize keyword relevancy checker."""
        # Initialize spaCy language model (use basic English model without external dependencies)
        self._nlp = English()

        logger.debug("Initialized KeywordRelevancyChecker with spaCy model")

    async def check_relevancy(
        self,
        document: RelevantDocument,
        query: str,
        config: RelevancyConfiguration,
        llm_credential_config: LLMCredentialConfig | None = None,  # noqa: ARG002
    ) -> float:
        """Check relevancy of document against query using keyword analysis.

        Args:
            document: Document to check for relevancy
            query: Query string to match against
            config: Configuration settings for keyword checking
            llm_credential_config: Unused — keyword checker does not use LLM

        Returns:
            Relevancy score between 0.0 and 1.0

        Raises:
            RelevancyCheckError: If relevancy checking fails

        """
        try:
            logger.debug("Starting keyword relevancy check for document", filename=document.file_metadata.filename)

            # Extract algorithm parameters
            params = config.algorithm_parameters
            case_sensitive = cast("bool", params.get("case_sensitive"))
            stem_words = cast("bool", params.get("stem_words"))
            remove_stopwords = cast("bool", params.get("remove_stopwords"))
            phrase_bonus_multiplier = cast("float", params.get("phrase_bonus_multiplier"))
            proximity_scoring = cast("bool", params.get("proximity_scoring"))
            fuzzy_matching = cast("bool", params.get("fuzzy_matching", RetrieverServiceDefaults.KEYWORD_FUZZY_MATCHING))

            # Use spaCy's built-in English stopwords
            stopwords = STOP_WORDS if remove_stopwords else set()

            # Preprocess query and document content
            processed_query = self._preprocess_text(
                query,
                case_sensitive=case_sensitive,
                stem_words=stem_words,
                remove_stopwords=remove_stopwords,
                stopwords=stopwords,
            )
            processed_content = self._preprocess_text(
                document.content,
                case_sensitive=case_sensitive,
                stem_words=stem_words,
                remove_stopwords=remove_stopwords,
                stopwords=stopwords,
            )
            processed_filename = self._preprocess_text(
                document.file_metadata.filename,
                case_sensitive=case_sensitive,
                stem_words=stem_words,
                remove_stopwords=remove_stopwords,
                stopwords=stopwords,
            )

            # Calculate scoring components using scikit-learn TF-IDF
            content_score = self._calculate_content_score_tfidf(
                query,
                document.content,
                case_sensitive=case_sensitive,
                remove_stopwords=remove_stopwords,
                stem_words=stem_words,
            )
            filename_score = self._calculate_filename_score(processed_query, processed_filename)
            phrase_score = self._calculate_phrase_score(
                query, document.content, phrase_bonus_multiplier, case_sensitive=case_sensitive
            )

            proximity_score = 0.0
            if proximity_scoring:
                proximity_score = self._calculate_proximity_score(processed_query, processed_content)

            exact_match_score = self._calculate_exact_match_score(
                query, document.content, case_sensitive=case_sensitive
            )

            fuzzy_score = 0.0
            if fuzzy_matching:
                fuzzy_score = self._calculate_fuzzy_match_score(query, document.content, case_sensitive=case_sensitive)

            # Apply configuration weights
            weights = config.ranking_weights
            final_score = (
                content_score * weights.get("term_frequency", RetrieverServiceDefaults.KEYWORD_RANKING_TERM_FREQUENCY)
                + filename_score
                * weights.get("filename_match", RetrieverServiceDefaults.KEYWORD_RANKING_FILENAME_MATCH)
                + phrase_score
                * weights.get("content_density", RetrieverServiceDefaults.KEYWORD_RANKING_CONTENT_DENSITY)
                + proximity_score
                * weights.get("proximity_bonus", RetrieverServiceDefaults.KEYWORD_RANKING_PROXIMITY_BONUS)
                + exact_match_score
                * weights.get("exact_match_bonus", RetrieverServiceDefaults.KEYWORD_RANKING_EXACT_MATCH_BONUS)
                + fuzzy_score
                * weights.get("fuzzy_match_bonus", RetrieverServiceDefaults.KEYWORD_RANKING_FUZZY_MATCH_BONUS)
            )

            # Normalize to 0.0-1.0 range
            final_score = min(1.0, max(0.0, final_score))

            logger.debug(
                "Keyword relevancy check completed",
                filename=document.file_metadata.filename,
                final_score=final_score,
                content_score=content_score,
                filename_score=filename_score,
                phrase_score=phrase_score,
                proximity_score=proximity_score,
                exact_match_score=exact_match_score,
                fuzzy_score=fuzzy_score,
            )

            return final_score

        except Exception as e:
            logger.exception("Keyword relevancy check failed for document", filename=document.file_metadata.filename)
            error_msg = f"Keyword relevancy check failed: {e!s}"
            raise RelevancyCheckError(error_msg) from e

    def _preprocess_text(
        self,
        text: str,
        *,
        case_sensitive: bool,
        stem_words: bool,
        remove_stopwords: bool,
        stopwords: set[str],
    ) -> list[str]:
        """Preprocess text by tokenizing and applying text processing options.

        Args:
            text: Text to preprocess
            case_sensitive: Whether to preserve case
            stem_words: Whether to apply spaCy lemmatization
            remove_stopwords: Whether to remove stopwords
            stopwords: Set of stopwords to remove from tokens

        Returns:
            List of processed tokens

        """
        if not text:
            return []

        # Convert to lowercase if not case-sensitive
        if not case_sensitive:
            text = text.lower()

        # Tokenize using spaCy
        doc = self._nlp(text)
        tokens = [token.text for token in doc if token.is_alpha]

        # Remove stopwords if enabled (case-insensitive comparison)
        if remove_stopwords:
            tokens = [token for token in tokens if token.lower() not in stopwords]

        # Apply spaCy lemmatization if enabled (better than stemming)
        if stem_words:
            doc = self._nlp(" ".join(tokens))
            tokens = [token.lemma_ for token in doc if token.is_alpha]

        return tokens

    def _calculate_content_score_tfidf(
        self, query: str, content: str, *, case_sensitive: bool, remove_stopwords: bool, stem_words: bool
    ) -> float:
        """Calculate content relevancy score using scikit-learn TF-IDF and cosine similarity.

        Args:
            query: Original query string
            content: Document content
            case_sensitive: Whether to preserve case
            remove_stopwords: Whether to remove stopwords
            stem_words: Whether to apply stemming

        Returns:
            Content relevancy score using TF-IDF and cosine similarity

        """
        if not query or not content:
            return 0.0

        # Prepare documents for TF-IDF
        documents = [query, content]

        # Configure TfidfVectorizer
        stop_words_list = None
        if remove_stopwords:
            # Use spaCy's built-in English stopwords
            stop_words_list = list(STOP_WORDS)

        # Create custom preprocessor for stemming if enabled
        def custom_preprocessor(text: str) -> str:
            if not case_sensitive:
                text = text.lower()
            return text

        def custom_tokenizer(text: str) -> list[str]:
            doc = self._nlp(text.lower() if not case_sensitive else text)
            tokens: list[str] = [token.text for token in doc if token.is_alpha]
            if stem_words:
                doc_for_lemma = self._nlp(" ".join(tokens))
                tokens = [token.lemma_ for token in doc_for_lemma if token.is_alpha]
            return tokens

        try:
            # Create TF-IDF vectorizer
            if stem_words:
                vectorizer = TfidfVectorizer(
                    stop_words=stop_words_list,
                    preprocessor=custom_preprocessor,
                    tokenizer=custom_tokenizer,
                    ngram_range=(1, 2),  # Include bigrams for phrase detection
                    max_features=10000,
                )
            else:
                vectorizer = TfidfVectorizer(
                    stop_words=stop_words_list, lowercase=not case_sensitive, ngram_range=(1, 2), max_features=10000
                )

            # Fit and transform documents
            tfidf_matrix = vectorizer.fit_transform(documents)

            # Calculate cosine similarity between query and content
            similarity_matrix = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])

            # Extract the similarity score
            similarity_score = float(similarity_matrix[0][0])

            return min(1.0, max(0.0, similarity_score))

        except (ValueError, TypeError, ImportError, LookupError) as e:
            logger.warning("TF-IDF calculation failed, falling back to manual method", error=str(e))
            # Fallback to original method if TF-IDF fails
            processed_query = self._preprocess_text(
                query,
                case_sensitive=case_sensitive,
                stem_words=stem_words,
                remove_stopwords=remove_stopwords,
                stopwords=set(STOP_WORDS),
            )
            processed_content = self._preprocess_text(
                content,
                case_sensitive=case_sensitive,
                stem_words=stem_words,
                remove_stopwords=remove_stopwords,
                stopwords=set(STOP_WORDS),
            )
            return self._calculate_content_score_fallback(processed_query, processed_content)

    def _calculate_content_score_fallback(self, query_tokens: list[str], content_tokens: list[str]) -> float:
        """Calculate TF-IDF based content relevancy score.

        Args:
            query_tokens: Processed query tokens
            content_tokens: Processed content tokens

        Returns:
            Content relevancy score

        """
        if not query_tokens or not content_tokens:
            return 0.0

        # Count term frequencies
        content_freq = Counter(content_tokens)
        content_length = len(content_tokens)

        # Calculate TF-IDF score for query terms
        score = 0.0
        query_length = len(query_tokens)

        for term in set(query_tokens):
            if term in content_freq:
                # Term frequency (normalized by document length)
                tf = content_freq[term] / content_length

                # Query term frequency (how important this term is in the query)
                query_tf = query_tokens.count(term) / query_length

                # Simple IDF approximation (log of inverse frequency)
                # In a full implementation, this would use corpus statistics
                idf = log(1000 / (content_freq[term] + 1))

                term_score = tf * idf * query_tf
                score += term_score

        # Normalize by query length
        return score / len(set(query_tokens))

    def _calculate_filename_score(self, query_tokens: list[str], filename_tokens: list[str]) -> float:
        """Calculate filename matching score.

        Args:
            query_tokens: Processed query tokens
            filename_tokens: Processed filename tokens

        Returns:
            Filename matching score

        """
        if not query_tokens or not filename_tokens:
            return 0.0

        # Count matches
        matches = 0
        for token in query_tokens:
            if token in filename_tokens:
                matches += 1

        # Return ratio of matched terms
        return matches / len(query_tokens)

    def _calculate_phrase_score(self, query: str, content: str, multiplier: float, *, case_sensitive: bool) -> float:
        """Calculate phrase matching score with bonus for exact phrases.

        Args:
            query: Original query string
            content: Original document content
            multiplier: Multiplier for phrase matches
            case_sensitive: Whether matching is case sensitive

        Returns:
            Phrase matching score

        """
        if not query or not content:
            return 0.0

        # Apply case sensitivity
        search_query = query if case_sensitive else query.lower()
        search_content = content if case_sensitive else content.lower()

        # Split query into potential phrases (2+ words)
        query_words = search_query.split()
        if len(query_words) < RetrieverServiceDefaults.KEYWORD_MINIMUM_QUERY_WORDS:
            return 0.0

        phrase_score = 0.0

        # Check for exact phrase matches
        if search_query in search_content:
            phrase_score += 1.0 * multiplier

        # Check for partial phrase matches (consecutive word pairs)
        for i in range(len(query_words) - 1):
            phrase = f"{query_words[i]} {query_words[i + 1]}"
            if phrase in search_content:
                phrase_score += 0.5 * multiplier

        # Normalize by potential maximum (all words as phrases)
        max_possible = (1.0 + 0.5 * (len(query_words) - 1)) * multiplier
        return phrase_score / max_possible if max_possible > 0 else 0.0

    def _calculate_proximity_score(self, query_tokens: list[str], content_tokens: list[str]) -> float:
        """Calculate proximity score based on how close query terms appear in content.

        Args:
            query_tokens: Processed query tokens
            content_tokens: Processed content tokens

        Returns:
            Proximity score

        """
        if len(query_tokens) < RetrieverServiceDefaults.KEYWORD_MINIMUM_QUERY_WORDS or not content_tokens:
            return 0.0

        # Find positions of query terms in content
        term_positions = self._find_term_positions(query_tokens, content_tokens)

        if len(term_positions) < RetrieverServiceDefaults.KEYWORD_MINIMUM_QUERY_WORDS:
            return 0.0

        # Calculate minimum distances between different query terms
        min_distances = self._calculate_term_distances(query_tokens, term_positions)

        if not min_distances:
            return 0.0

        # Convert distances to proximity score
        return self._convert_distances_to_score(min_distances)

    def _find_term_positions(self, query_tokens: list[str], content_tokens: list[str]) -> dict[str, list[int]]:
        """Find positions of query terms in content."""
        term_positions: dict[str, list[int]] = {}
        for i, token in enumerate(content_tokens):
            if token in query_tokens:
                if token not in term_positions:
                    term_positions[token] = []
                term_positions[token].append(i)
        return term_positions

    def _calculate_term_distances(self, query_tokens: list[str], term_positions: dict[str, list[int]]) -> list[int]:
        """Calculate minimum distances between different query terms."""
        min_distances = []
        query_terms = list(set(query_tokens))

        for i in range(len(query_terms)):
            for j in range(i + 1, len(query_terms)):
                term1, term2 = query_terms[i], query_terms[j]
                if term1 in term_positions and term2 in term_positions:
                    min_dist = self._find_minimum_distance(term_positions[term1], term_positions[term2])
                    if min_dist != float("inf"):
                        min_distances.append(int(min_dist))

        return min_distances

    def _find_minimum_distance(self, positions1: list[int], positions2: list[int]) -> float:
        """Find minimum distance between any occurrences of two terms."""
        min_dist = float("inf")
        for pos1 in positions1:
            for pos2 in positions2:
                min_dist = min(min_dist, abs(pos1 - pos2))
        return min_dist

    def _convert_distances_to_score(self, min_distances: list[int]) -> float:
        """Convert distances to proximity score."""
        # Score based on proximity (closer = higher score)
        avg_distance = sum(min_distances) / len(min_distances)

        # Convert distance to score (1.0 for adjacent terms, decreasing with distance)
        distance_normalization_factor = 10.0
        return 1.0 / (1.0 + avg_distance / distance_normalization_factor)

    def _calculate_exact_match_score(self, query: str, content: str, *, case_sensitive: bool) -> float:
        """Calculate score for exact matches of the query in content.

        Args:
            query: Original query string
            content: Original document content
            case_sensitive: Whether matching is case sensitive

        Returns:
            Exact match score

        """
        if not query or not content:
            return 0.0

        # Prepare for matching
        search_query = query if case_sensitive else query.lower()
        search_content = content if case_sensitive else content.lower()

        # Count exact occurrences
        count = search_content.count(search_query)

        if count == 0:
            return 0.0

        # Score based on frequency, normalized by content length
        content_length = len(search_content.split())
        normalized_score = (count * len(search_query.split())) / content_length

        # Cap at 1.0
        exact_match_boost_factor = 2.0  # Multiply by 2 to boost exact matches
        return min(1.0, normalized_score * exact_match_boost_factor)

    def _calculate_fuzzy_match_score(self, query: str, content: str, *, case_sensitive: bool) -> float:
        """Calculate fuzzy matching score using rapidfuzz algorithms.

        Args:
            query: Original query string
            content: Document content
            case_sensitive: Whether matching is case sensitive

        Returns:
            Fuzzy matching score based on similarity algorithms

        """
        if not query or not content:
            return 0.0

        # Prepare text for comparison
        search_query = query if case_sensitive else query.lower()
        search_content = content if case_sensitive else content.lower()

        # Split into words for token-level comparison
        query_words = search_query.split()
        content_words = search_content.split()

        if not query_words or not content_words:
            return 0.0

        # Calculate fuzzy scores for each query word against all content words
        total_score = 0.0
        for query_word in query_words:
            best_match_score = 0.0
            for content_word in content_words:
                # Use Jaro-Winkler for fuzzy string similarity (good for typos)
                jaro_score = JaroWinkler.normalized_similarity(query_word, content_word)
                # Use Levenshtein for edit distance (good for similar words)
                levenshtein_score = fuzz.ratio(query_word, content_word) / 100.0
                # Combine both scores
                combined_score = (jaro_score + levenshtein_score) / 2.0
                best_match_score = max(best_match_score, combined_score)
            total_score += best_match_score

        # Normalize by number of query words
        fuzzy_score = total_score / len(query_words)

        # Apply threshold - only return score if above minimum similarity
        fuzzy_threshold = 0.6  # Minimum similarity threshold
        if fuzzy_score < fuzzy_threshold:
            return 0.0

        # Normalize to 0.0-1.0 range
        return min(1.0, max(0.0, fuzzy_score))
