"""Performance test helpers shared across integration test suites.

Extracted from the migrated performance tests to resolve stale
``tests.performance.conftest`` import paths.
"""

from __future__ import annotations

import io

_TEXT_LINE = "Performance test content — lorem ipsum dolor sit amet. " * 4 + "\n"


def compute_percentile(values: list[float], percentile: float) -> float:
    """Compute a percentile from a sorted list using linear interpolation."""
    if not 0 <= percentile <= 100:
        msg = f"percentile must be between 0 and 100, got {percentile}"
        raise ValueError(msg)
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    k = (n - 1) * (percentile / 100)
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_vals[-1]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def generate_text_content(size_kb: int = 64) -> bytes:
    """Generate plain-text content of approximately *size_kb* kilobytes."""
    target = size_kb * 1024
    buf = io.BytesIO()
    line = _TEXT_LINE.encode()
    while buf.tell() < target:
        buf.write(line)
    return buf.getvalue()[:target]


def generate_pdf_content(size_kb: int = 128) -> bytes:
    """Generate a valid PDF of approximately *size_kb* kilobytes using pypdf."""
    from pypdf import PdfWriter

    target = size_kb * 1024
    writer = PdfWriter()
    pages_needed = max(1, target // 1536)
    for _ in range(pages_needed):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
