"""Performance tests for utility functions.

This module tests that utility functions meet performance requirements:
- Filter parsing: <1ms per operation
- Pagination helper: <5ms per operation
"""

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from syntara.core.models.base import NamedResource
from syntara.core.utils import matches, parse_filters, parse_label_filter
from syntara.core.utils.cursor import SortDirection, create_cursor_data, decode_cursor, encode_cursor
from syntara.core.utils.pagination import PaginationResult, generate_response
from syntara.core.utils.sorting import parse_sort

if TYPE_CHECKING:
    from syntara.core.utils import CursorData


class MockResource(NamedResource):
    """Mock resource class for testing performance."""

    def __init__(self) -> None:
        """Initialize mock resource with mock attributes."""
        super().__init__(id=uuid4(), created_at=datetime.now(UTC), updated_at=datetime.now(UTC), name="Test")


class TestFilterParserPerformance:
    """Test parse_filters performance requirements."""

    def test_filter_parser_simple_performance(self) -> None:
        """Test filter parser with simple parameters (<1ms)."""
        params = {"name": "test-resource", "status": "active"}
        allowed_fields = ["name", "status", "created_at"]

        start_time = time.perf_counter()

        # Run parsing 100 times to get average
        filters = []
        for _ in range(100):
            filters = parse_filters(params, allowed_fields)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 100

        # Should be under 1ms (0.001 seconds)
        assert avg_time < 0.001, f"Filter parsing took {avg_time:.4f}s, expected <0.001s"
        assert len(filters) == 2

    def test_filter_parser_complex_performance(self) -> None:
        """Test filter parser with complex bracket notation (<1ms)."""
        params = {
            "name[contains]": "service",
            "status[eq]": "active",
            "created_at[gte]": "2025-01-01T00:00:00Z",
            "updated_at[lt]": "2025-12-31T23:59:59Z",
            "priority[gt]": "5",
        }
        allowed_fields = ["name", "status", "created_at", "updated_at", "priority"]

        start_time = time.perf_counter()

        # Run parsing 100 times to get average
        filters = []
        for _ in range(100):
            filters = parse_filters(params, allowed_fields)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 100

        # Should be under 5ms (0.005 seconds)
        assert avg_time < 0.005, f"Complex filter parsing took {avg_time:.4f}s, expected <0.005s"
        assert len(filters) == 5

    def test_filter_parser_large_params_performance(self) -> None:
        """Test filter parser with many parameters (<1ms)."""
        # Create 20 filter parameters
        params = {}
        allowed_fields = []

        for i in range(20):
            field_name = f"field_{i}"
            params[f"{field_name}[eq]"] = f"value_{i}"
            allowed_fields.append(field_name)

        start_time = time.perf_counter()

        # Run parsing 50 times to get average
        filters = []
        for _ in range(50):
            filters = parse_filters(params, allowed_fields)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 50

        # Should be under 1ms (0.001 seconds)
        assert avg_time < 0.001, f"Large params parsing took {avg_time:.4f}s, expected <0.001s"
        assert len(filters) == 20


class TestPaginationHelperPerformance:
    """Test PaginationHelper performance requirements."""

    def test_cursor_encoding_performance(self) -> None:
        """Test cursor encoding performance (<5ms)."""
        resource = MockResource()

        start_time = time.perf_counter()

        # Run encoding 1000 times to get average
        cursor = ""
        for _ in range(1000):
            cursor_data = create_cursor_data(resource_id=resource.id, created_at=resource.created_at)
            cursor = encode_cursor(cursor_data)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 1000

        # Should be under 5ms (0.005 seconds)
        assert avg_time < 0.005, f"Cursor encoding took {avg_time:.4f}s, expected <0.005s"
        assert len(cursor) > 0

    def test_cursor_decoding_performance(self) -> None:
        """Test cursor decoding performance (<5ms)."""
        resource = MockResource()
        cursor_data = create_cursor_data(resource_id=resource.id, created_at=resource.created_at)
        cursor = encode_cursor(cursor_data)

        start_time = time.perf_counter()

        # Run decoding 1000 times to get average
        decoded: CursorData = {}
        for _ in range(1000):
            decoded = decode_cursor(cursor)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 1000

        # Should be under 5ms (0.005 seconds)
        assert avg_time < 0.005, f"Cursor decoding took {avg_time:.4f}s, expected <0.005s"
        assert "id" in decoded

    def test_pagination_response_generation_performance(self) -> None:
        """Test pagination response generation performance (<5ms)."""
        # Create list of mock resources
        resources = [MockResource() for _ in range(20)]

        start_time = time.perf_counter()

        # Run response generation 100 times to get average
        response: PaginationResult
        for _ in range(100):
            response = generate_response(
                items=resources,
                limit=20,
                cursor=None,
                include_total=True,
                total_count=100,
            )

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 100

        # Should be under 5ms (0.005 seconds)
        assert avg_time < 0.005, f"Pagination response took {avg_time:.4f}s, expected <0.005s"
        assert "next" in response

    def test_large_pagination_performance(self) -> None:
        """Test pagination with large item lists (<5ms)."""
        # Create list of 100 mock resources
        resources = [MockResource() for _ in range(100)]

        start_time = time.perf_counter()

        # Run response generation 50 times to get average
        response: PaginationResult
        for _ in range(50):
            response = generate_response(
                items=resources,
                limit=100,
                cursor=None,
                include_total=True,
                total_count=1000,
            )

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 50

        # Should be under 5ms (0.005 seconds)
        assert avg_time < 0.005, f"Large pagination took {avg_time:.4f}s, expected <0.005s"
        assert response["total"] == 1000


class TestSortParserPerformance:
    """Test SortParser performance requirements."""

    def test_sort_parser_simple_performance(self) -> None:
        """Test sort parser with simple parameters (<1ms)."""
        allowed_fields = ["name", "created_at", "updated_at", "priority"]

        start_time = time.perf_counter()

        # Run parsing 1000 times to get average
        field = ""
        for _ in range(1000):
            field, _ = parse_sort(sort_param="-created_at", allowed_fields=allowed_fields)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 1000

        # Should be under 1ms (0.001 seconds)
        assert avg_time < 0.001, f"Sort parsing took {avg_time:.4f}s, expected <0.001s"
        assert field == "created_at"

    def test_sort_parser_multiple_performance(self) -> None:
        """Test sort parser with multiple sort parameters (<1ms)."""
        sort_params = ["name", "-created_at", "priority", "-updated_at"]
        allowed_fields = ["name", "created_at", "updated_at", "priority"]

        start_time = time.perf_counter()

        # Run parsing 100 times to get average (using individual parse_sort calls)
        results = []
        for _ in range(100):
            parsed_sorts = []
            for sort_param in sort_params:
                field, direction = parse_sort(
                    sort_param, allowed_fields, default_field="", default_direction=SortDirection.ASC
                )
                parsed_sorts.append((field, direction))
            results = parsed_sorts

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 100

        # Should be under 1ms (0.001 seconds)
        assert avg_time < 0.001, f"Multiple sort parsing took {avg_time:.4f}s, expected <0.001s"
        assert len(results) == 4


class TestLabelFilterPerformance:
    """Test label filter functions performance requirements."""

    def test_label_matching_performance(self) -> None:
        """Test label matching performance (<1ms)."""
        resource_labels = {
            "environment": "production",
            "region": "us-east-1",
            "team": "platform",
            "service": "api",
            "version": "v1.2.3",
        }
        filter_labels = {"environment": "production", "region": "us-east-1"}

        start_time = time.perf_counter()

        # Run matching 1000 times to get average
        result = False
        for _ in range(1000):
            result = matches(resource_labels, filter_labels)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 1000

        # Should be under 1ms (0.001 seconds)
        assert avg_time < 0.001, f"Label matching took {avg_time:.4f}s, expected <0.001s"
        assert result is True

    def test_label_filter_parsing_performance(self) -> None:
        """Test label filter parsing performance (<1ms)."""
        params = {
            "labels[environment]": "production",
            "labels[region]": "us-east-1",
            "labels[team]": "platform",
            "labels[service]": "api",
            "labels[version]": "v1.2.3",
            "other_param": "ignored",
            "another_param": "also_ignored",
        }

        start_time = time.perf_counter()

        # Run parsing 1000 times to get average
        label_filters = {}
        for _ in range(1000):
            label_filters = parse_label_filter(params)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 1000

        # Should be under 1ms (0.001 seconds)
        assert avg_time < 0.001, f"Label filter parsing took {avg_time:.4f}s, expected <0.001s"
        assert len(label_filters) == 5

    def test_large_label_set_performance(self) -> None:
        """Test performance with large label sets (<1ms)."""
        # Create resource with 50 labels
        resource_labels = {f"label_{i}": f"value_{i}" for i in range(50)}

        # Create filter with 10 labels (subset)
        filter_labels = {f"label_{i}": f"value_{i}" for i in range(0, 20, 2)}

        start_time = time.perf_counter()

        # Run matching 100 times to get average
        result = False
        for _ in range(100):
            result = matches(resource_labels, filter_labels)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 100

        # Should be under 1ms (0.001 seconds)
        assert avg_time < 0.001, f"Large label matching took {avg_time:.4f}s, expected <0.001s"
        assert result is True


class TestCombinedOperationsPerformance:
    """Test performance of combined utility operations."""

    def test_full_query_processing_performance(self) -> None:
        """Test combined filter, sort, and pagination processing (<10ms)."""
        # Simulate a complex query
        filter_params = {"name[contains]": "service", "status": "active", "created_at[gte]": "2025-01-01T00:00:00Z"}
        label_params = {"labels[environment]": "production", "labels[region]": "us-east-1"}
        sort_param = "-created_at"
        resources = [MockResource() for _ in range(20)]

        allowed_fields = ["name", "status", "created_at", "updated_at"]

        start_time = time.perf_counter()

        # Run full processing 50 times to get average
        for _ in range(50):
            # Parse filters
            _ = parse_filters(filter_params, allowed_fields)

            # Parse labels
            _ = parse_label_filter(label_params)

            # Parse sort
            _, _ = parse_sort(sort_param, allowed_fields)

            # Generate pagination
            _ = generate_response(items=resources, limit=20, cursor=None)

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 50

        # Should be under 10ms (0.01 seconds) for combined operations
        assert avg_time < 0.01, f"Combined operations took {avg_time:.4f}s, expected <0.01s"
