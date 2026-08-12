"""Suite 20 — File Upload & Document Conversion: Resource Consumption (20.5).

Test 20.5: Process-level memory usage during document conversion
    KPI: Resource Consumption — memory bounded
    Validation: Process-level memory monitoring via psutil

Run with:
    make test-integration-coverage
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable


logger = structlog.stdlib.get_logger(__name__)

# ---------------------------------------------------------------------------
# Process-level memory monitoring (no oc required)
# ---------------------------------------------------------------------------

MEMORY_THRESHOLD_MB = 100
MEMORY_SAMPLE_RATE_S = 0.1


async def _measure_peak_memory[T](
    coro: Awaitable[T],
) -> tuple[T, float]:
    """Run *coro* while sampling RSS and return (result, increase_mb).

    Uses ``psutil`` to track the peak RSS of the current process while
    the coroutine is executing.
    """
    import asyncio

    import psutil  # type: ignore[import-untyped]

    process = psutil.Process()
    baseline_mb = process.memory_info().rss / 1024 / 1024
    peak_mb = baseline_mb

    stop = asyncio.Event()

    async def _sample() -> None:
        nonlocal peak_mb
        while not stop.is_set():
            current = process.memory_info().rss / 1024 / 1024
            peak_mb = max(peak_mb, current)
            try:
                await asyncio.wait_for(stop.wait(), timeout=MEMORY_SAMPLE_RATE_S)
            except TimeoutError:
                pass

    task = asyncio.create_task(_sample())
    try:
        result = await coro
    finally:
        stop.set()
        await task

    return result, peak_mb - baseline_mb


class TestProcessMemoryDuringConversion:
    """20.5 — Process-level memory usage during document conversion.

    Uses ``psutil`` to monitor RSS of the current process while running
    converters directly.  This complements the pod-level monitoring above
    and works without ``oc`` or an OpenShift cluster.

    Validates:
        - Memory increase < 100 MB for 8 MB text conversion
        - Memory increase < 150 MB for 3 MB PDF conversion
        - Memory increase < 200 MB for 3 concurrent 2 MB text conversions
    """

    @pytest.mark.asyncio
    async def test_memory_during_large_text_conversion(self) -> None:
        """8 MB text conversion must not spike memory by > 100 MB."""
        from syntara.files.document_conversion.converters.text_converter import TextConverter
        from tests.integration.files.helpers import make_file_metadata
        from tests.integration.helpers.perf import generate_text_content

        content = generate_text_content(8 * 1024)
        metadata = make_file_metadata(content, suffix=".txt")

        converter = TextConverter()
        result, increase_mb = await _measure_peak_memory(
            converter.convert(content, metadata),
        )

        logger.info(
            "Text conversion memory usage",
            size_mb=len(content) / (1024 * 1024),
            increase_mb=round(increase_mb, 1),
        )

        assert result.success, "Text conversion should succeed"
        assert increase_mb < MEMORY_THRESHOLD_MB, (
            f"Memory increased by {increase_mb:.1f} MB during 8 MB text "
            f"conversion, exceeding {MEMORY_THRESHOLD_MB} MB threshold"
        )

    @pytest.mark.asyncio
    async def test_memory_during_pdf_conversion(self) -> None:
        """3 MB PDF conversion must not spike memory by > 150 MB."""
        from syntara.files.document_conversion.converters.pdf_converter import PDFConverter
        from tests.integration.files.helpers import make_file_metadata
        from tests.integration.helpers.perf import generate_pdf_content

        content = generate_pdf_content(3 * 1024)
        metadata = make_file_metadata(content, suffix=".pdf")
        pdf_threshold = MEMORY_THRESHOLD_MB * 1.5

        converter = PDFConverter()
        result, increase_mb = await _measure_peak_memory(
            converter.convert(content, metadata),
        )

        logger.info(
            "PDF conversion memory usage",
            size_mb=len(content) / (1024 * 1024),
            increase_mb=round(increase_mb, 1),
        )

        assert result is not None, "PDF converter returned None"
        assert increase_mb < pdf_threshold, (
            f"Memory increased by {increase_mb:.1f} MB during 3 MB PDF "
            f"conversion, exceeding {pdf_threshold:.0f} MB threshold"
        )

    @pytest.mark.asyncio
    async def test_memory_during_concurrent_conversions(self) -> None:
        """3 concurrent 2 MB text conversions must not spike memory by > 200 MB."""
        import asyncio

        from syntara.files.document_conversion.converters.text_converter import TextConverter
        from tests.integration.files.helpers import make_file_metadata
        from tests.integration.helpers.perf import generate_text_content

        if TYPE_CHECKING:
            from syntara.files.models import FileMetadata

        concurrent_threshold = MEMORY_THRESHOLD_MB * 2
        file_pairs: list[tuple[bytes, FileMetadata]] = []
        for _ in range(3):
            content = generate_text_content(2 * 1024)
            metadata = make_file_metadata(content, suffix=".txt")
            file_pairs.append((content, metadata))

        converter = TextConverter()
        results, increase_mb = await _measure_peak_memory(
            asyncio.gather(*[converter.convert(c, m) for c, m in file_pairs]),
        )

        logger.info(
            "Concurrent conversion memory usage",
            file_count=len(file_pairs),
            size_mb_each=2.0,
            increase_mb=round(increase_mb, 1),
        )

        for result in results:
            assert result.success, "Concurrent text conversion should succeed"

        assert increase_mb < concurrent_threshold, (
            f"Memory increased by {increase_mb:.1f} MB during concurrent "
            f"conversions, exceeding {concurrent_threshold:.0f} MB threshold"
        )
