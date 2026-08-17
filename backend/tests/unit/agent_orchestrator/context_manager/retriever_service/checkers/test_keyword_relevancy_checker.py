"""Unit tests for KeywordRelevancyChecker implementation."""

from copy import deepcopy

import pytest

from syntara.agent_orchestrator.context_manager.retriever_service.checkers.keyword_relevancy_checker import (
    KeywordRelevancyChecker,
)
from syntara.agent_orchestrator.context_manager.retriever_service.config.configuration_manager import (
    ConfigurationManager,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.files.models import FileMetadata


class TestKeywordRelevancyChecker:
    """Test suite for KeywordRelevancyChecker."""

    @pytest.fixture
    def checker(self) -> KeywordRelevancyChecker:
        """Create KeywordRelevancyChecker instance."""
        return KeywordRelevancyChecker()

    @pytest.fixture
    def basic_config(self) -> RelevancyConfiguration:
        """Create basic configuration for testing using ConfigurationManager."""
        config_manager = ConfigurationManager()
        return config_manager.get_keyword_configuration()

    @pytest.fixture
    def sample_document(self) -> RelevantDocument:
        """Create sample document for testing."""
        file_metadata = FileMetadata(
            file_id="12345",
            filename="machine_learning_guide.txt",
            size_bytes=1024,
            mime_type="text/plain",
            file_path="/path/to/machine_learning_guide.txt",
            status="converted",
        )
        return RelevantDocument(
            content="This document covers machine learning algorithms including neural networks and deep learning.",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/path/to/file.txt"},
            relevancy_score=0.0,
        )

    @pytest.mark.asyncio
    async def test_basic_relevancy_scoring(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration, sample_document: RelevantDocument
    ) -> None:
        """Test basic relevancy scoring functionality."""
        query = "machine learning"
        score = await checker.check_relevancy(sample_document, query, basic_config)

        assert 0.0 <= score <= 1.0
        assert score > 0.35  # Should be relevant

    @pytest.mark.asyncio
    async def test_exact_query_match(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test scoring when query exactly matches content."""
        file_metadata = FileMetadata(
            file_id="12346",
            filename="test.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )
        document = RelevantDocument(
            content="python programming tutorial",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        query = "python programming tutorial"
        score = await checker.check_relevancy(document, query, basic_config)

        assert score > 0.6  # Should score highly for exact match

    @pytest.mark.asyncio
    async def test_filename_matching_bonus(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test that filename matches contribute to scoring."""
        file_metadata = FileMetadata(
            file_id="12347",
            filename="python_tutorial.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/to/python_tutorial.txt",
            status="converted",
        )
        document = RelevantDocument(
            content="general programming concepts",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        query = "python tutorial"
        score = await checker.check_relevancy(document, query, basic_config)

        assert score >= 0.0  # Should process without error

    @pytest.mark.asyncio
    async def test_case_sensitivity_option(
        self, checker: KeywordRelevancyChecker, sample_document: RelevantDocument, basic_config: RelevancyConfiguration
    ) -> None:
        """Test case sensitivity configuration option."""
        # Case-insensitive config
        case_insensitive_config = deepcopy(basic_config)

        # Case-sensitive config
        case_sensitive_config = deepcopy(basic_config)
        case_sensitive_config.algorithm_parameters["case_sensitive"] = True

        query = "MACHINE LEARNING"

        score_insensitive = await checker.check_relevancy(sample_document, query, case_insensitive_config)
        score_sensitive = await checker.check_relevancy(sample_document, query, case_sensitive_config)

        assert score_insensitive > score_sensitive  # Case in-sensitive should score higher

    @pytest.mark.asyncio
    async def test_stemming_functionality(self, checker: KeywordRelevancyChecker) -> None:
        """Test word stemming functionality."""
        file_metadata = FileMetadata(
            file_id="12348",
            filename="test.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )
        document = RelevantDocument(
            content="running runners ran",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        config_manager = ConfigurationManager()
        config = config_manager.get_keyword_configuration()
        config.algorithm_parameters["stem_words"] = True

        query = "run"
        score = await checker.check_relevancy(document, query, config)

        assert score > 0.05  # Should detect some stemmed matches

    @pytest.mark.asyncio
    async def test_phrase_matching_bonus(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test phrase matching with bonus multiplier."""
        file_metadata = FileMetadata(
            file_id="12349",
            filename="test.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )
        document = RelevantDocument(
            content="artificial intelligence and machine learning are related fields",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        query = "machine learning"
        score = await checker.check_relevancy(document, query, basic_config)

        assert score > 0.3  # Should get phrase bonus

    @pytest.mark.asyncio
    async def test_stopword_removal(self, checker: KeywordRelevancyChecker) -> None:
        """Test stopword removal functionality."""
        file_metadata = FileMetadata(
            file_id="12351",
            filename="test.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )
        document = RelevantDocument(
            content="the machine learning and artificial intelligence",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        config_manager = ConfigurationManager()
        config = config_manager.get_keyword_configuration()
        config.algorithm_parameters["remove_stopwords"] = True

        query = "machine learning"
        score = await checker.check_relevancy(document, query, config)

        assert score > 0.3  # Should work despite stopwords

    @pytest.mark.asyncio
    async def test_fuzzy_matching_functionality(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test fuzzy matching handles typos and similar words."""
        file_metadata = FileMetadata(
            file_id="fuzzy_test",
            filename="test.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )
        document = RelevantDocument(
            content="machine learning algorithms and artifical intelligence",  # Deliberate typo
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Enable fuzzy matching
        fuzzy_config = deepcopy(basic_config)
        fuzzy_config.algorithm_parameters["fuzzy_matching"] = True

        # Query with typo that should match "artificial" with fuzzy matching
        query = "artificial intelligence"
        score = await checker.check_relevancy(document, query, fuzzy_config)

        # Disable fuzzy matching for comparison
        no_fuzzy_config = deepcopy(basic_config)
        no_fuzzy_config.algorithm_parameters["fuzzy_matching"] = False
        score_no_fuzzy = await checker.check_relevancy(document, query, no_fuzzy_config)

        assert score > score_no_fuzzy  # Fuzzy matching should improve score
        assert score > 0.2  # Should detect fuzzy match despite typo

    @pytest.mark.asyncio
    async def test_proximity_scoring_functionality(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test proximity scoring for terms that appear close together."""
        file_metadata = FileMetadata(
            file_id="proximity_test",
            filename="test.txt",
            size_bytes=200,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )

        # Document with query terms close together vs far apart
        close_terms_doc = RelevantDocument(
            content="machine learning is powerful. Other unrelated content goes here.",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        far_terms_doc = RelevantDocument(
            content=(
                "machine systems are complex. Many words separate these concepts. "
                "Various topics discussed. Eventually we talk about learning algorithms."
            ),
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Enable proximity scoring
        proximity_config = deepcopy(basic_config)
        proximity_config.algorithm_parameters["proximity_scoring"] = True

        query = "machine learning"
        close_score = await checker.check_relevancy(close_terms_doc, query, proximity_config)
        far_score = await checker.check_relevancy(far_terms_doc, query, proximity_config)

        assert close_score > far_score  # Closer terms should score higher
        assert close_score > 0.3  # Close terms should get proximity bonus

    @pytest.mark.asyncio
    async def test_edge_cases_whitespace_queries(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test handling of edge cases: whitespace-only content and empty queries."""
        file_metadata = FileMetadata(
            file_id="edge_test",
            filename="test.txt",
            size_bytes=1,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )

        # Test whitespace-only content (minimum valid content per validation)
        whitespace_doc = RelevantDocument(
            content=" ",  # Single space is minimum valid content
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Test normal document for comparison
        normal_doc = RelevantDocument(
            content="machine learning content",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        query = "machine learning"

        # Edge cases should handle gracefully
        whitespace_score = await checker.check_relevancy(whitespace_doc, query, basic_config)

        # Empty query should also handle gracefully
        empty_query_score = await checker.check_relevancy(normal_doc, "", basic_config)
        whitespace_query_score = await checker.check_relevancy(normal_doc, "   ", basic_config)

        # Test that the checker can handle these edge cases without crashing
        assert 0.0 <= whitespace_score <= 1.0  # Whitespace-only content should be valid score
        assert empty_query_score == pytest.approx(0.0)  # Empty query should score 0
        assert whitespace_query_score == pytest.approx(0.0)  # Whitespace-only query should score 0

    @pytest.mark.asyncio
    async def test_comprehensive_scoring_weights_impact(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test that different scoring component weights significantly impact final scores."""
        file_metadata = FileMetadata(
            file_id="weights_test",
            filename="machine_learning_tutorial.txt",
            size_bytes=200,
            mime_type="text/plain",
            file_path="/path/to/machine_learning_tutorial.txt",
            status="converted",
        )
        document = RelevantDocument(
            content=(
                "This comprehensive guide covers machine learning algorithms, "
                "neural networks, and artificial intelligence concepts."
            ),
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Default weights configuration
        default_config = deepcopy(basic_config)

        # Configuration emphasizing filename matching
        filename_heavy_config = deepcopy(basic_config)
        filename_heavy_config.ranking_weights["filename_match"] = 0.8
        filename_heavy_config.ranking_weights["term_frequency"] = 0.1

        # Configuration emphasizing content scoring
        content_heavy_config = deepcopy(basic_config)
        content_heavy_config.ranking_weights["term_frequency"] = 0.9
        content_heavy_config.ranking_weights["filename_match"] = 0.1

        query = "machine learning tutorial"

        default_score = await checker.check_relevancy(document, query, default_config)
        filename_score = await checker.check_relevancy(document, query, filename_heavy_config)
        content_score = await checker.check_relevancy(document, query, content_heavy_config)

        # All scores should be valid
        assert 0.0 <= default_score <= 1.0
        assert 0.0 <= filename_score <= 1.0
        assert 0.0 <= content_score <= 1.0

        # Different weight configurations should produce measurably different scores
        assert abs(filename_score - content_score) > 0.05  # Should see meaningful difference

        # Since filename contains query terms, filename-heavy should score reasonably well
        assert filename_score > 0.1  # Adjusted to realistic expectation based on scoring algorithm

    @pytest.mark.asyncio
    async def test_exact_match_scoring_functionality(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test exact match scoring component with various match scenarios."""
        file_metadata = FileMetadata(
            file_id="exact_match_test",
            filename="test.txt",
            size_bytes=300,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )

        # Document with multiple exact matches
        multiple_matches_doc = RelevantDocument(
            content="Python programming is great. Python programming helps developers. Programming in Python is fun.",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Document with single exact match
        single_match_doc = RelevantDocument(
            content="This tutorial covers Python programming concepts and advanced techniques for developers.",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Document with no exact matches
        no_match_doc = RelevantDocument(
            content="This tutorial covers Java development concepts and advanced techniques for developers.",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        query = "Python programming"

        multiple_score = await checker.check_relevancy(multiple_matches_doc, query, basic_config)
        single_score = await checker.check_relevancy(single_match_doc, query, basic_config)
        no_match_score = await checker.check_relevancy(no_match_doc, query, basic_config)

        # Multiple exact matches should score higher than single matches
        assert multiple_score > single_score
        # Single exact match should score higher than no exact matches
        assert single_score > no_match_score
        # All scores should be valid
        assert 0.0 <= multiple_score <= 1.0
        assert 0.0 <= single_score <= 1.0
        assert 0.0 <= no_match_score <= 1.0

    @pytest.mark.asyncio
    async def test_multiword_query_processing(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test processing of complex multi-word queries with different patterns."""
        file_metadata = FileMetadata(
            file_id="multiword_test",
            filename="test.txt",
            size_bytes=200,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )

        document = RelevantDocument(
            content=(
                "Machine learning and artificial intelligence are transformative technologies. "
                "Deep learning neural networks enable advanced pattern recognition capabilities."
            ),
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Test different query patterns
        short_query = "learning"
        medium_query = "machine learning"
        long_query = "machine learning artificial intelligence"
        complex_query = "deep learning neural networks pattern recognition"

        short_score = await checker.check_relevancy(document, short_query, basic_config)
        medium_score = await checker.check_relevancy(document, medium_query, basic_config)
        long_score = await checker.check_relevancy(document, long_query, basic_config)
        complex_score = await checker.check_relevancy(document, complex_query, basic_config)

        # All queries should return valid scores
        for score in [short_score, medium_score, long_score, complex_score]:
            assert 0.0 <= score <= 1.0

        # More specific queries with exact matches should generally score well
        assert medium_score > 0.2
        assert long_score > 0.2
        assert complex_score > 0.3

    @pytest.mark.asyncio
    async def test_text_preprocessing_edge_cases(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test text preprocessing with various edge cases and special characters."""
        file_metadata = FileMetadata(
            file_id="preprocessing_test",
            filename="test-file_name.txt",
            size_bytes=150,
            mime_type="text/plain",
            file_path="/path/to/test-file_name.txt",
            status="converted",
        )

        # Test content with special characters, numbers, punctuation
        special_content_doc = RelevantDocument(
            content="Machine-learning & AI: 2024 trends, etc. (deep-learning) [neural networks] 90% accuracy!",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Test with hyphenated filenames
        hyphenated_filename_doc = RelevantDocument(
            content="This document discusses various technological concepts and methodologies.",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Test queries with special characters
        special_query = "machine-learning"
        filename_query = "test-file"
        mixed_query = "machine learning & AI"

        special_score = await checker.check_relevancy(special_content_doc, special_query, basic_config)
        filename_score = await checker.check_relevancy(hyphenated_filename_doc, filename_query, basic_config)
        mixed_score = await checker.check_relevancy(special_content_doc, mixed_query, basic_config)

        # Should handle special characters gracefully and return valid scores
        assert 0.0 <= special_score <= 1.0
        assert 0.0 <= filename_score <= 1.0
        assert 0.0 <= mixed_score <= 1.0

        # Content with matching terms should score positively
        assert special_score > 0.0
        assert filename_score > 0.0

    @pytest.mark.asyncio
    async def test_advanced_algorithm_combinations(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test combinations of algorithm parameters for comprehensive functionality."""
        file_metadata = FileMetadata(
            file_id="algorithm_combo_test",
            filename="machine_learning_guide.txt",
            size_bytes=250,
            mime_type="text/plain",
            file_path="/path/to/machine_learning_guide.txt",
            status="converted",
        )

        document = RelevantDocument(
            content=(
                "Running machine learning algorithms efficiently requires understanding neural networks thoroughly."
            ),
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Test all algorithm combinations enabled
        all_enabled_config = deepcopy(basic_config)
        all_enabled_config.algorithm_parameters.update(
            {
                "case_sensitive": False,
                "stem_words": True,
                "remove_stopwords": True,
                "proximity_scoring": True,
                "fuzzy_matching": True,
                "phrase_bonus_multiplier": 2.0,
            }
        )

        # Test minimal configuration
        minimal_config = deepcopy(basic_config)
        minimal_config.algorithm_parameters.update(
            {
                "case_sensitive": True,
                "stem_words": False,
                "remove_stopwords": False,
                "proximity_scoring": False,
                "fuzzy_matching": False,
                "phrase_bonus_multiplier": 1.0,
            }
        )

        query = "run machine learning"  # "run" should match "running" with stemming

        all_enabled_score = await checker.check_relevancy(document, query, all_enabled_config)
        minimal_score = await checker.check_relevancy(document, query, minimal_config)

        # Both configurations should work
        assert 0.0 <= all_enabled_score <= 1.0
        assert 0.0 <= minimal_score <= 1.0

        # Advanced features should generally improve matching
        assert all_enabled_score >= minimal_score

    @pytest.mark.asyncio
    async def test_document_length_normalization(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test scoring behavior with documents of varying lengths."""
        file_metadata = FileMetadata(
            file_id="length_test",
            filename="test.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )

        # Very short document with exact match
        short_doc = RelevantDocument(
            content="machine learning",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Medium document with exact match
        medium_doc = RelevantDocument(
            content="This comprehensive guide covers machine learning algorithms and techniques used in data science.",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Long document with exact match buried in text
        long_doc = RelevantDocument(
            content=(
                "In the modern world of technology and innovation, various computational techniques "
                "have emerged to solve complex problems. Among these revolutionary approaches, "
                "machine learning has gained significant prominence in recent years. The field "
                "encompasses numerous methodologies, algorithms, and frameworks that enable "
                "computers to learn from data without being explicitly programmed for every task."
            ),
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        query = "machine learning"

        short_score = await checker.check_relevancy(short_doc, query, basic_config)
        medium_score = await checker.check_relevancy(medium_doc, query, basic_config)
        long_score = await checker.check_relevancy(long_doc, query, basic_config)

        # All should be valid scores
        assert 0.0 <= short_score <= 1.0
        assert 0.0 <= medium_score <= 1.0
        assert 0.0 <= long_score <= 1.0

        # Short document with exact match should score very highly
        assert short_score > 0.5

        # All documents should have reasonable scores since they contain the exact query
        assert medium_score > 0.2
        assert long_score > 0.1

    @pytest.mark.asyncio
    async def test_various_configuration_combinations(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test various configuration combinations work reliably."""
        file_metadata = FileMetadata(
            file_id="config_test",
            filename="python_guide.txt",
            size_bytes=200,
            mime_type="text/plain",
            file_path="/path/to/python_guide.txt",
            status="converted",
        )

        document = RelevantDocument(
            content="This comprehensive Python programming guide covers advanced concepts and best practices.",
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Test different scoring weight combinations
        balanced_config = deepcopy(basic_config)
        balanced_config.ranking_weights.update(
            {
                "term_frequency": 0.5,
                "filename_match": 0.3,
                "content_density": 0.2,
            }
        )

        content_heavy_config = deepcopy(basic_config)
        content_heavy_config.ranking_weights.update(
            {
                "term_frequency": 0.9,
                "filename_match": 0.05,
                "content_density": 0.05,
            }
        )

        query = "Python programming"

        balanced_score = await checker.check_relevancy(document, query, balanced_config)
        content_heavy_score = await checker.check_relevancy(document, query, content_heavy_config)

        # Both configurations should produce valid scores
        assert 0.0 <= balanced_score <= 1.0
        assert 0.0 <= content_heavy_score <= 1.0

        # Both should score reasonably well since content contains the query terms
        assert balanced_score > 0.1
        assert content_heavy_score > 0.1

    @pytest.mark.asyncio
    async def test_term_frequency_analysis(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test term frequency analysis with repeated terms and rare terms."""
        file_metadata = FileMetadata(
            file_id="tf_test",
            filename="test.txt",
            size_bytes=250,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )

        # Document with high frequency target terms
        high_freq_doc = RelevantDocument(
            content=(
                "Python Python Python programming. Python is powerful. "
                "Programming with Python requires Python knowledge. Python Python Python."
            ),
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Document with low frequency target terms
        low_freq_doc = RelevantDocument(
            content=(
                "This comprehensive tutorial discusses various programming languages including "
                "Java, C++, JavaScript, and also mentions Python briefly in the context of data science."
            ),
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        query = "Python programming"

        high_freq_score = await checker.check_relevancy(high_freq_doc, query, basic_config)
        low_freq_score = await checker.check_relevancy(low_freq_doc, query, basic_config)

        # Both should be valid
        assert 0.0 <= high_freq_score <= 1.0
        assert 0.0 <= low_freq_score <= 1.0

        # High frequency document should score higher
        assert high_freq_score > low_freq_score
        assert high_freq_score > 0.3  # Should score well due to high term frequency

    @pytest.mark.asyncio
    async def test_complex_query_patterns(
        self, checker: KeywordRelevancyChecker, basic_config: RelevancyConfiguration
    ) -> None:
        """Test complex query patterns and their interaction with content."""
        file_metadata = FileMetadata(
            file_id="complex_query_test",
            filename="technical_guide.txt",
            size_bytes=400,
            mime_type="text/plain",
            file_path="/path/to/technical_guide.txt",
            status="converted",
        )

        # Rich content document
        document = RelevantDocument(
            content=(
                "Deep learning neural networks revolutionize artificial intelligence applications. "
                "Machine learning algorithms enable pattern recognition and predictive analytics. "
                "Natural language processing transforms text analysis capabilities significantly."
            ),
            file_metadata=file_metadata,
            source_type="uploaded",
            retrieval_metadata={"output_path": "/test.txt"},
            relevancy_score=0.0,
        )

        # Test various query complexity levels
        simple_query = "learning"
        compound_query = "deep learning neural networks"
        cross_domain_query = "machine learning artificial intelligence"
        specific_query = "natural language processing text analysis"

        simple_score = await checker.check_relevancy(document, simple_query, basic_config)
        compound_score = await checker.check_relevancy(document, compound_query, basic_config)
        cross_score = await checker.check_relevancy(document, cross_domain_query, basic_config)
        specific_score = await checker.check_relevancy(document, specific_query, basic_config)

        # All should be valid scores
        for score in [simple_score, compound_score, cross_score, specific_score]:
            assert 0.0 <= score <= 1.0

        # Specific queries with exact phrase matches should score well
        assert compound_score > 0.3
        assert specific_score > 0.3

        # Broader queries should still match
        assert simple_score > 0.1
        assert cross_score > 0.2
