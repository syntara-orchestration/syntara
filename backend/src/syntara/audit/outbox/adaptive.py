"""Adaptive polling and batch sizing state machine for audit outbox worker.

Dynamically adjusts both poll interval and batch size based on backlog trends
to optimize database connection usage and event processing throughput.
"""

from __future__ import annotations

import structlog

logger = structlog.stdlib.get_logger(__name__)


class AdaptiveOutboxStateMachine:
    """State machine for adaptive audit outbox polling and batch sizing.

    Adjusts both poll interval and batch size based on backlog trends rather than
    absolute values:
    - Speeds up polling + increases batch when backlog is growing (falling behind)
    - Slows down polling + decreases batch when backlog is shrinking (catching up)
    - Resets to baseline when empty (reduce DB load)

    The state machine tracks pending count across polls and scales both parameters
    using multiplicative factors, bounded to prevent runaway adjustment.

    Example progression (base_interval=5s, base_batch=100):
        Poll 1: 0 pending    → (6.5s, 100)   empty, exponential cooldown (5s * 1.3)
        Poll 2: 0 pending    → (8.45s, 100)  still empty, cooldown continues (6.5s * 1.3)
        Poll 3: 500 pending  → (5s, 100)     first cycle with backlog, seed & return base
        Poll 4: 1200 pending → (3.5s, 130)   delta=700 > batch → GROWING_MODERATE
        Poll 5: 1500 pending → (1.75s, 195)  delta=300 > batch → GROWING_MODERATE
        Poll 6: 800 pending  → (2.275s, 150) delta=-700 < 0 → SHRINKING
        Poll 7: 100 pending  → (2.957s, 115) delta=-700 < 0 → SHRINKING
        Poll 8: 0 pending    → (3.844s, 100) empty, batch resets, interval cools down (2.957s * 1.3)
    """

    # Scaling factors for adjustment (multiplicative)
    SCALE_GROWING_FAST = (0.5, 1.5)  # (interval, batch) - delta > 2x batch
    SCALE_GROWING_MODERATE = (0.7, 1.3)  # delta > 1x batch
    SCALE_GROWING_SLOW = (0.85, 1.15)  # delta > 0
    SCALE_STABLE = (1.0, 1.0)  # delta within stable threshold
    SCALE_SHRINKING = (1.3, 0.77)  # delta < 0 (catching up)

    # Bounds (multipliers of base values)
    MIN_INTERVAL_MULTIPLIER = 0.2  # Max speed (1s if base=5s)
    MAX_INTERVAL_MULTIPLIER = 6.0  # Idle mode (30s if base=5s)
    MIN_BATCH_MULTIPLIER = 1.0  # Never go below base
    MAX_BATCH_MULTIPLIER = 10.0  # Max 10x base (1000 if base=100)

    STABLE_THRESHOLD_PCT = 0.1  # ±10% of current backlog = stable

    def __init__(self, base_interval: float, base_batch_size: int) -> None:
        """Initialize state machine.

        Args:
            base_interval: Baseline poll interval from settings (seconds)
            base_batch_size: Baseline batch size from settings

        """
        self._base_interval = base_interval
        self._base_batch_size = base_batch_size
        self._previous_pending_count: int | None = None  # None = first cycle
        self._current_interval = base_interval
        self._current_batch_size = base_batch_size

    def calculate_next_parameters(self, current_pending: int) -> tuple[float, int]:
        """Calculate next (poll_interval, batch_size) based on backlog trend.

        Args:
            current_pending: Current number of events in outbox

        Returns:
            (interval_seconds, batch_size) for next cycle

        """
        # Empty queue - exponential cooldown for interval, reset batch to base
        if current_pending == 0:
            self._previous_pending_count = 0
            self._current_batch_size = self._base_batch_size
            # Gradually slow down interval instead of instant idle jump
            max_idle = self._base_interval * self.MAX_INTERVAL_MULTIPLIER
            self._current_interval = min(self._current_interval * self.SCALE_SHRINKING[0], max_idle)
            logger.debug(
                "Adaptive: cooldown (queue empty)",
                interval_seconds=self._current_interval,
                batch_size=self._current_batch_size,
            )
            return (self._current_interval, self._current_batch_size)

        # First cycle after initialization - seed previous count, return base values
        # Skips delta calculation to avoid cold-start overcorrection (0 → 500 → GROWING_FAST spike)
        if self._previous_pending_count is None:
            self._previous_pending_count = current_pending
            logger.debug(
                "Adaptive: first cycle (seeding previous count)",
                current_pending=current_pending,
                interval_seconds=self._current_interval,
                batch_size=self._current_batch_size,
            )
            return (self._current_interval, self._current_batch_size)

        # Calculate backlog change (trend)
        delta = current_pending - self._previous_pending_count

        # Determine scaling factors based on trend
        interval_scale, batch_scale = self._get_scaling_factors(delta, current_pending)

        # Apply scaling with bounds
        new_interval = self._clamp_interval(self._current_interval * interval_scale)
        new_batch_size = self._clamp_batch_size(self._current_batch_size * batch_scale)
        new_batch_size_int = int(new_batch_size)

        # Log transition for observability
        logger.debug(
            "Adaptive: parameters adjusted",
            previous_pending=self._previous_pending_count,
            current_pending=current_pending,
            delta=delta,
            interval_scale=interval_scale,
            batch_scale=batch_scale,
            previous_interval=self._current_interval,
            new_interval=new_interval,
            previous_batch_size=self._current_batch_size,
            new_batch_size=new_batch_size_int,
        )

        # Update state for next cycle
        self._previous_pending_count = current_pending
        self._current_interval = new_interval
        self._current_batch_size = new_batch_size_int

        return (new_interval, new_batch_size_int)

    def _get_scaling_factors(self, delta: int, current_pending: int) -> tuple[float, float]:
        """Determine (interval, batch) scaling factors based on backlog change.

        Args:
            delta: Change in pending count since last poll
            current_pending: Current number of events in outbox

        Returns:
            (interval_scale, batch_scale) to apply to current values

        """
        # Check stable first (within ±10% of current backlog or ±10 events, whichever larger)
        # Scales with backlog depth to prevent false stability at high backlogs
        stable_threshold = max(10, int(current_pending * self.STABLE_THRESHOLD_PCT))
        if abs(delta) <= stable_threshold:
            return self.SCALE_STABLE  # Maintain current values

        # Backlog growing - speed up polling, increase batch size progressively
        # Use current adaptive batch_size (not static base) for threshold comparisons
        if delta > self._current_batch_size * 2:
            return self.SCALE_GROWING_FAST  # Growing fast - aggressive adjustment
        if delta > self._current_batch_size:
            return self.SCALE_GROWING_MODERATE  # Growing moderately
        if delta > 0:
            return self.SCALE_GROWING_SLOW  # Growing slowly - slight adjustment

        # Backlog shrinking - slow down polling, decrease batch (we're keeping up)
        return self.SCALE_SHRINKING

    def _clamp_interval(self, interval: float) -> float:
        """Clamp interval to reasonable bounds.

        Args:
            interval: Proposed interval

        Returns:
            Clamped interval within [min_interval, max_interval]

        """
        min_interval = self._base_interval * self.MIN_INTERVAL_MULTIPLIER
        max_interval = self._base_interval * self.MAX_INTERVAL_MULTIPLIER
        return max(min_interval, min(max_interval, interval))

    def _clamp_batch_size(self, batch_size: float) -> float:
        """Clamp batch size to reasonable bounds.

        Args:
            batch_size: Proposed batch size

        Returns:
            Clamped batch size within [min_batch, max_batch]

        """
        min_batch = self._base_batch_size * self.MIN_BATCH_MULTIPLIER
        max_batch = self._base_batch_size * self.MAX_BATCH_MULTIPLIER
        return max(min_batch, min(max_batch, batch_size))

    def reset(self) -> None:
        """Reset state machine to initial state."""
        self._previous_pending_count = None
        self._current_interval = self._base_interval
        self._current_batch_size = self._base_batch_size
        logger.debug(
            "Adaptive: state machine reset",
            interval_seconds=self._current_interval,
            batch_size=self._current_batch_size,
        )

    @property
    def current_interval(self) -> float:
        """Get current poll interval without updating state."""
        return self._current_interval

    @property
    def current_batch_size(self) -> int:
        """Get current batch size without updating state."""
        return self._current_batch_size
