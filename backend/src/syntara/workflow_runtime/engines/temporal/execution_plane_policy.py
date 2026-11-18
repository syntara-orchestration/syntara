"""Build Temporal retry configuration from recorded EP settings."""

from datetime import timedelta
from typing import Any

from temporalio.common import RetryPolicy

EP_POLICY_SNAPSHOT_KEY = "_execution_plane_policy"


def build_ep_retry_policy(ep_settings: dict[str, Any]) -> RetryPolicy:
    """Use recorded settings, with defaults for histories that predate them."""
    return RetryPolicy(
        maximum_attempts=ep_settings.get("ep_dispatch_max_retries", 3) + 1,
        initial_interval=timedelta(seconds=ep_settings.get("ep_dispatch_initial_backoff_seconds", 0.5)),
        maximum_interval=timedelta(seconds=ep_settings.get("ep_dispatch_max_backoff_seconds", 10.0)),
        backoff_coefficient=2.0,
    )
