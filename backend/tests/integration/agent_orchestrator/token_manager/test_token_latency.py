"""Performance test for token calculation latency.

Tests that token calculation meets performance targets:
- p95 latency < 50ms per calculation
"""

import statistics
import time

import structlog

from syntara.agent_orchestrator.token_manager.services import TokenCalculator

logger = structlog.stdlib.get_logger(__name__)


class TestTokenCalculationLatency:
    """Performance tests for token calculation speed."""

    def test_token_calculation_latency_meets_target(self) -> None:
        """Test that token calculation completes within 50ms (p95).

        Target: <50ms per calculation (p95)
        Test: Calculate tokens for 1000 requests of varying sizes
        """
        calculator = TokenCalculator()

        # Generate test texts of varying sizes
        test_texts = [
            "Short text " * 10,  # ~50 tokens
            "Medium length text for testing token counting performance " * 20,  # ~200 tokens
            "This is a longer text that simulates a more realistic LLM request with multiple sentences and paragraphs. "
            * 50,  # ~500 tokens
            "Very long text " * 200,  # ~1000 tokens
        ]

        # Run 1000 token calculations
        latencies: list[float] = []
        num_iterations = 1000

        for i in range(num_iterations):
            text = test_texts[i % len(test_texts)]

            start_time = time.perf_counter()
            calculator.count_tokens(text)
            end_time = time.perf_counter()

            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)

        # Calculate percentiles
        latencies.sort()
        p50 = statistics.median(latencies)
        p95_index = int(0.95 * len(latencies))
        p95 = latencies[p95_index]
        p99_index = int(0.99 * len(latencies))
        p99 = latencies[p99_index]

        # Report results and verify against target
        logger.info(
            "Token calculation latency results",
            iterations=num_iterations,
            p50_ms=round(p50, 2),
            p95_ms=round(p95, 2),
            p99_ms=round(p99, 2),
            min_ms=round(min(latencies), 2),
            max_ms=round(max(latencies), 2),
            mean_ms=round(statistics.mean(latencies), 2),
        )
        diag = (
            f"\n--- Token calculation latency (n={num_iterations}) ---\n"
            f"  p50={p50:.2f}ms, p95={p95:.2f}ms, p99={p99:.2f}ms\n"
            f"  min={min(latencies):.2f}ms, max={max(latencies):.2f}ms, "
            f"mean={statistics.mean(latencies):.2f}ms\n"
        )
        assert p95 < 50.0, f"p95 latency {p95:.2f}ms exceeds target of 50ms{diag}"

    def test_encoder_caching_effectiveness(self) -> None:
        """Test that the @lru_cache on _get_encoder means the encoder is created only once.

        Uses cache_info() rather than wall-clock timing: sub-microsecond operations
        are dominated by OS scheduling jitter, making timing-based assertions
        unreliable in CI environments.
        """
        from syntara.agent_orchestrator.token_manager.services import _get_encoder

        calculator = TokenCalculator()

        cache_before = _get_encoder.cache_info()

        # Use 20 distinct texts so _count_tokens_cached misses each time,
        # exercising _get_encoder on every call and proving it is cached.
        for i in range(20):
            calculator.count_tokens(f"unique caching validation text {i} " * 10)

        cache_after = _get_encoder.cache_info()

        new_misses = cache_after.misses - cache_before.misses
        new_hits = cache_after.hits - cache_before.hits

        logger.info(
            "Encoder caching effectiveness",
            new_misses=new_misses,
            new_hits=new_hits,
            total_misses=cache_after.misses,
            total_hits=cache_after.hits,
        )

        # Encoder should be created at most once (first call) and reused for the rest.
        assert new_misses <= 1, (
            f"_get_encoder should be created at most once via lru_cache, but had {new_misses} new misses"
        )
        assert new_hits >= 19, (
            f"_get_encoder should be served from cache for all subsequent calls, but only got {new_hits} new hits"
        )

    def test_token_calculation_scales_linearly(self) -> None:
        """Test that token calculation time scales linearly with text length.

        Verifies that performance doesn't degrade exponentially with longer texts.
        """
        calculator = TokenCalculator()

        text_sizes = [100, 500, 1000, 2000, 5000]  # Number of words
        results = []

        for size in text_sizes:
            text = "word " * size
            latencies = []

            for _ in range(50):
                start_time = time.perf_counter()
                calculator.count_tokens(text)
                end_time = time.perf_counter()
                latencies.append((end_time - start_time) * 1000)

            mean_latency = statistics.mean(latencies)
            results.append((size, mean_latency))
            logger.debug("Scaling data point", words=size, mean_ms=round(mean_latency, 2))

        # Check that latency scales reasonably (not exponentially)
        # 5000 words is 50x more than 100 words
        # Linear scaling would be ~50x, exponential would be >>100x
        # Allow up to 80x to account for constant overhead and CI variability
        # Note: CI environments have higher overhead for small inputs
        ratio = results[-1][1] / results[0][1]

        logger.info(
            "Token calculation scaling test results",
            smallest_words=results[0][0],
            smallest_ms=round(results[0][1], 2),
            largest_words=results[-1][0],
            largest_ms=round(results[-1][1], 2),
            scaling_ratio=round(ratio, 1),
            target_ratio_max=80.0,
        )

        assert ratio < 80.0, (
            f"Latency scaling is too steep (exponential): {ratio:.1f}x "
            f"({results[0][0]} words={results[0][1]:.2f}ms, "
            f"{results[-1][0]} words={results[-1][1]:.2f}ms)"
        )
        logger.info("✅ Token calculation scales linearly with text length")
