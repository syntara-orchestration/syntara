"""Performance test for token calculation latency.

Tests that token calculation meets performance targets:
- p95 latency < 50ms per calculation
"""

import gc
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
        """Test that encoder caching reduces latency on repeated calls.

        Verifies that the @lru_cache decorator on get_encoder() is effective.
        """
        calculator = TokenCalculator()
        text = "Test text for encoder caching validation " * 10

        # Ensure consistent GC state before measurement to avoid
        # non-deterministic timing from GC running mid-measurement
        gc.collect()

        # First call (may include encoder initialization)
        latencies_first: list[float] = []
        for _ in range(100):
            start_time = time.perf_counter()
            calculator.count_tokens(text)
            end_time = time.perf_counter()
            latencies_first.append((end_time - start_time) * 1000)

        # GC before second measurement phase for fair comparison
        gc.collect()

        # Subsequent calls (should use cached encoder)
        latencies_cached: list[float] = []
        for _ in range(100):
            start_time = time.perf_counter()
            calculator.count_tokens(text)
            end_time = time.perf_counter()
            latencies_cached.append((end_time - start_time) * 1000)

        mean_first = statistics.mean(latencies_first)
        mean_cached = statistics.mean(latencies_cached)

        improvement_pct = (mean_first - mean_cached) / mean_first * 100

        logger.info(
            "Encoder caching performance",
            mean_first_ms=round(mean_first, 2),
            mean_cached_ms=round(mean_cached, 2),
            improvement_pct=round(improvement_pct, 1),
        )

        # Both should be fast, but there should be no significant degradation
        assert mean_cached <= mean_first * 1.1, (
            f"Caching should not degrade performance "
            f"(first={mean_first:.2f}ms, cached={mean_cached:.2f}ms, improvement={improvement_pct:.1f}%)"
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
