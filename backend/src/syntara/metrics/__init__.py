"""Metrics subsystem for recording and exposing performance metrics.

This module provides the infrastructure for recording raw performance metrics
from Nexus components (LLM, cache, workflow, agent) and exposing them via
a Prometheus-compatible OpenMetrics scrape endpoint at ``/metrics``.

Nexus records and exposes raw metrics data. KPI calculations (p95, averages,
aggregations) are performed by external performance tests, not by Nexus.
"""
