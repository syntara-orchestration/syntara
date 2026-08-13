"""Intentionally failing test to validate the xfail-from-url mechanism."""

import pytest


def test_always_fails():
    pytest.fail("This test is intentionally broken to validate xfail-from-url")
