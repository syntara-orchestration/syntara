"""Unit tests for Uvicorn SSL context factory."""

from __future__ import annotations

import ssl
from unittest.mock import MagicMock

from syntara.api.main import _ssl_context_factory


class TestSslContextFactory:
    """Tests for _ssl_context_factory()."""

    def test_wraps_default_factory_and_sets_minimum_version(self) -> None:
        """Test that the factory wraps the default and enforces TLS 1.3."""
        mock_config = MagicMock()
        mock_default_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

        def mock_default_factory() -> ssl.SSLContext:
            return mock_default_ctx

        ctx = _ssl_context_factory(mock_config, mock_default_factory)

        assert ctx is mock_default_ctx
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3
