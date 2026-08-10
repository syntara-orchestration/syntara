"""Metrics subsystem for recording and exposing performance metrics.

This module provides the infrastructure for recording raw performance metrics
from Syntara components (LLM, cache, workflow, agent) and exposing them via
a Prometheus-compatible OpenMetrics scrape endpoint at ``/metrics``.

Syntara records and exposes raw metrics data. KPI calculations (p95, averages,
aggregations) are performed by external performance tests, not by Syntara.
"""
