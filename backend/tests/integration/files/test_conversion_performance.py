"""Suite 20 — File Upload & Document Conversion: Conversion Performance (20.6).

Tests document converter performance: time budgets (NFR-001) and throughput.

KPIs:
    - PDF conversion < 30s for 2 MB (NFR-001)
    - Text conversion < 30s for 5 MB (NFR-001)
    - Service-level text conversion < 5s for 1 MB
    - Text converter throughput > 10 MB/s across file sizes
Measurement: Component-level timing (direct converter invocation)

Run with:
    make test-integration-coverage
"""

from __future__ import annotations

import time

import pytest
import structlog

from syntara.files.document_conversion.converters.pdf_converter import PDFConverter
from syntara.files.document_conversion.converters.text_converter import TextConverter
from tests.integration.files.helpers import make_file_metadata
from tests.integration.helpers.perf import generate_pdf_content, generate_text_content

logger = structlog.stdlib.get_logger(__name__)

TARGET_CONVERSION_TIME_S = 30.0
SERVICE_LEVEL_TARGET_S = 5.0
TARGET_THROUGHPUT_MB_PER_S = 10.0

SIZE_2MB_KB = 2 * 1024
SIZE_5MB_KB = 5 * 1024
SIZE_1MB_KB = 1024
BENCHMARK_SIZES_KB = [100, 500, 1024, 2048]


class TestConversionTime:
    """20.6 — Document conversion time within NFR-001 budget.

    Exercises the PDF and text converters directly to measure conversion
    wall-clock time without network overhead.  This isolates the
    CPU/disk-intensive conversion cost from the upload API path.

    Validates:
        - 2 MB PDF conversion < 30s
        - 5 MB text conversion < 30s
        - 1 MB text service-level conversion < 5s
    """

    @pytest.mark.asyncio
    async def test_pdf_conversion_under_30_seconds(self) -> None:
        """2 MB PDF conversion must complete within 30s (NFR-001)."""
        content = generate_pdf_content(SIZE_2MB_KB)
        metadata = make_file_metadata(content, suffix=".pdf")

        converter = PDFConverter()
        start = time.monotonic()
        result = await converter.convert(content, metadata)
        elapsed_s = time.monotonic() - start

        logger.info(
            "PDF conversion completed",
            size_mb=len(content) / (1024 * 1024),
            elapsed_s=round(elapsed_s, 2),
            success=result.success if result else False,
        )

        assert result is not None, "PDF converter returned None"
        assert elapsed_s < TARGET_CONVERSION_TIME_S, (
            f"PDF conversion took {elapsed_s:.2f}s, exceeding {TARGET_CONVERSION_TIME_S}s limit"
        )

    @pytest.mark.asyncio
    async def test_text_conversion_under_30_seconds(self) -> None:
        """5 MB text conversion must complete within 30s (NFR-001)."""
        content = generate_text_content(SIZE_5MB_KB)
        metadata = make_file_metadata(content, suffix=".txt")

        converter = TextConverter()
        start = time.monotonic()
        result = await converter.convert(content, metadata)
        elapsed_s = time.monotonic() - start

        logger.info(
            "Text conversion completed",
            size_mb=len(content) / (1024 * 1024),
            elapsed_s=round(elapsed_s, 2),
            success=result.success,
        )

        assert result.success, "Text conversion failed"
        assert elapsed_s < TARGET_CONVERSION_TIME_S, (
            f"Text conversion took {elapsed_s:.2f}s, exceeding {TARGET_CONVERSION_TIME_S}s limit"
        )

    @pytest.mark.asyncio
    async def test_service_level_text_conversion_under_5_seconds(self) -> None:
        """1 MB text conversion via TextConverter must complete within 5s."""
        content = generate_text_content(SIZE_1MB_KB)
        metadata = make_file_metadata(content, suffix=".txt")

        converter = TextConverter()
        start = time.monotonic()
        result = await converter.convert(content, metadata)
        elapsed_s = time.monotonic() - start

        logger.info(
            "Service-level text conversion completed",
            size_mb=len(content) / (1024 * 1024),
            elapsed_s=round(elapsed_s, 2),
            success=result.success,
        )

        assert result.success, "Text conversion failed"
        assert elapsed_s < SERVICE_LEVEL_TARGET_S, (
            f"Service-level text conversion took {elapsed_s:.2f}s, exceeding {SERVICE_LEVEL_TARGET_S}s limit"
        )


class TestConverterThroughput:
    """20.6 — Text converter throughput benchmark.

    Benchmarks the TextConverter across multiple file sizes to track
    conversion throughput and detect regressions.

    Validates:
        - Throughput > 10 MB/s for each size tier
        - Conversion succeeds for all test sizes
    """

    @pytest.mark.asyncio
    async def test_text_converter_throughput(self) -> None:
        """Text converter must sustain > 10 MB/s across all file sizes."""
        converter = TextConverter()
        results: dict[str, dict[str, float]] = {}
        failures: list[str] = []

        for size_kb in BENCHMARK_SIZES_KB:
            content = generate_text_content(size_kb)
            metadata = make_file_metadata(content, suffix=".txt")

            start = time.monotonic()
            result = await converter.convert(content, metadata)
            elapsed_s = time.monotonic() - start

            size_mb = size_kb / 1024
            throughput = size_mb / elapsed_s if elapsed_s > 0 else 0

            label = f"{size_mb:.1f}MB"
            results[label] = {
                "elapsed_s": elapsed_s,
                "throughput_mb_s": throughput,
                "success": 1.0 if result.success else 0.0,
            }

            assert result.success, f"Text conversion failed for {label}"

            if throughput < TARGET_THROUGHPUT_MB_PER_S:
                failures.append(f"{label}: {throughput:.1f} MB/s")

            logger.info(
                "Converter benchmark result",
                size_mb=round(size_mb, 1),
                elapsed_s=round(elapsed_s, 4),
                throughput_mb_s=round(throughput, 1),
            )

        diag_parts = [
            "\n--- Text converter benchmark results (20.6) ---",
            f"  target throughput: > {TARGET_THROUGHPUT_MB_PER_S:.0f} MB/s",
        ]
        for label, stats in results.items():
            diag_parts.append(f"  {label}: {stats['elapsed_s']:.4f}s, {stats['throughput_mb_s']:.1f} MB/s")
        diag = "\n".join(diag_parts) + "\n"

        assert not failures, (
            f"Text converter throughput below {TARGET_THROUGHPUT_MB_PER_S:.0f} MB/s for: {'; '.join(failures)}{diag}"
        )
