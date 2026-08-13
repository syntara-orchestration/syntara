"""Unit tests for combined adaptive state machine."""

import pytest

from syntara.audit.outbox.adaptive import AdaptiveOutboxStateMachine


class TestAdaptiveOutboxStateMachine:
    """Test combined adaptive state machine for poll interval and batch size."""

    def test_initial_state(self) -> None:
        """State machine initializes with base values."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        assert sm.current_interval == 5.0
        assert sm.current_batch_size == 100

    def test_empty_queue_cooldown_and_reset_batch(self) -> None:
        """Empty queue triggers interval cooldown and resets batch to base."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._current_interval = 3.0
        sm._current_batch_size = 500

        interval, batch = sm.calculate_next_parameters(current_pending=0)

        # Interval: cooldown (3.0 * 1.3 = 3.9)
        assert interval == pytest.approx(3.9)
        # Batch: reset to base
        assert batch == 100

    def test_first_cycle_seeds_previous_count(self) -> None:
        """First cycle seeds previous count without adjustment (avoids cold-start spike)."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        assert sm._previous_pending_count is None

        # First cycle with 500 existing events - should seed and return base values
        interval, batch = sm.calculate_next_parameters(current_pending=500)
        assert interval == 5.0
        assert batch == 100
        assert sm._previous_pending_count == 500  # Seeded for next cycle

        # Second cycle - now delta calculation kicks in
        interval_2, batch_2 = sm.calculate_next_parameters(current_pending=650)
        # delta = 150 (> 100, < 200) → GROWING_MODERATE = (0.7, 1.3)
        assert interval_2 == pytest.approx(3.5)  # 5.0 * 0.7
        assert batch_2 == 130  # 100 * 1.3

    def test_growing_slowly(self) -> None:
        """Backlog growing slowly increases interval/batch by (0.85, 1.15)."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 100
        sm._current_interval = 5.0
        sm._current_batch_size = 100

        # delta = 50 (< 100) → GROWING_SLOW
        # stable_threshold = max(10, 150 * 0.1) = 15, delta=50 > 15
        interval, batch = sm.calculate_next_parameters(current_pending=150)
        assert interval == pytest.approx(4.25)  # 5.0 * 0.85
        assert batch == pytest.approx(115, abs=1)  # 100 * 1.15

    def test_growing_moderately(self) -> None:
        """Backlog growing moderately adjusts by (0.7, 1.3)."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 100
        sm._current_interval = 5.0
        sm._current_batch_size = 100

        # delta = 150 (> 100, < 200) → GROWING_MODERATE
        interval, batch = sm.calculate_next_parameters(current_pending=250)
        assert interval == 3.5  # 5.0 * 0.7
        assert batch == 130  # 100 * 1.3

    def test_growing_fast(self) -> None:
        """Backlog growing fast adjusts by (0.5, 1.5)."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 100
        sm._current_interval = 5.0
        sm._current_batch_size = 100

        # delta = 250 (> 200) → GROWING_FAST
        interval, batch = sm.calculate_next_parameters(current_pending=350)
        assert interval == 2.5  # 5.0 * 0.5
        assert batch == 150  # 100 * 1.5

    def test_stable_backlog(self) -> None:
        """Stable backlog maintains both values."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 500
        sm._current_interval = 3.0
        sm._current_batch_size = 200

        # delta = 40, stable_threshold = max(10, 540 * 0.1) = 54 → STABLE
        interval, batch = sm.calculate_next_parameters(current_pending=540)
        assert interval == 3.0  # maintained
        assert batch == 200  # maintained

    def test_shrinking_backlog(self) -> None:
        """Shrinking backlog adjusts by (1.3, 0.77)."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 500
        sm._current_interval = 2.0
        sm._current_batch_size = 300

        # delta = -100 (< 0) → SHRINKING
        interval, batch = sm.calculate_next_parameters(current_pending=400)
        assert interval == pytest.approx(2.6)  # 2.0 * 1.3
        assert batch == 231  # 300 * 0.77

    def test_interval_clamped_to_minimum(self) -> None:
        """Interval cannot go below 0.2x base."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 100
        sm._current_interval = 1.2
        sm._current_batch_size = 100

        # delta = 300 → GROWING_FAST (0.5x) → would be 0.6s, clamped to 1.0s
        interval, _ = sm.calculate_next_parameters(current_pending=400)
        assert interval == 1.0  # clamped to 5.0 * 0.2

    def test_interval_clamped_to_maximum(self) -> None:
        """Interval cannot exceed 6x base."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 100
        sm._current_interval = 28.0
        sm._current_batch_size = 100

        # delta = -50 → SHRINKING (1.3x) → would be 36.4s, clamped to 30s
        interval, _ = sm.calculate_next_parameters(current_pending=50)
        assert interval == 30.0  # clamped to 5.0 * 6.0

    def test_batch_clamped_to_minimum(self) -> None:
        """Batch size cannot go below 1x base."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 200
        sm._current_interval = 5.0
        sm._current_batch_size = 100

        # delta = -150 → SHRINKING (0.77x) → would be 77, clamped to 100
        _, batch = sm.calculate_next_parameters(current_pending=50)
        assert batch == 100  # clamped to base

    def test_batch_clamped_to_maximum(self) -> None:
        """Batch size cannot exceed 10x base."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 1000
        sm._current_interval = 1.0
        sm._current_batch_size = 1000

        # delta = 500 → GROWING_FAST (1.5x) → would be 1500, clamped to 1000
        _, batch = sm.calculate_next_parameters(current_pending=1500)
        assert batch == 1000  # clamped to 100 * 10

    def test_progressive_growth_scenario(self) -> None:
        """Simulate backlog growing progressively."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)

        # Start: empty → cooldown
        interval_1, batch_1 = sm.calculate_next_parameters(current_pending=0)
        assert interval_1 == pytest.approx(6.5)  # 5.0 * 1.3 (cooldown)
        assert batch_1 == 100

        # Backlog appears: 100 events (first non-zero cycle seeds)
        interval_2, batch_2 = sm.calculate_next_parameters(current_pending=100)
        # After empty, _previous = 0, so delta=100 (GROWING_SLOW since 100 = batch_size)
        # But stable_threshold = max(10, 100 * 0.1) = 10, delta=100 > 10
        # Actually delta=100 > batch_size (100) is FALSE, so GROWING_SLOW (0.85, 1.15)
        assert interval_2 == pytest.approx(5.525)  # 6.5 * 0.85
        assert batch_2 == pytest.approx(115, abs=1)  # 100 * 1.15

        # Growing moderately: +150
        interval_3, batch_3 = sm.calculate_next_parameters(current_pending=250)
        assert interval_3 < interval_2  # Sped up
        assert batch_3 > batch_2  # Increased

    def test_progressive_shrink_scenario(self) -> None:
        """Simulate backlog shrinking."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 1000
        sm._current_interval = 1.0
        sm._current_batch_size = 500

        # Shrinking: 1000 → 700
        interval_1, batch_1 = sm.calculate_next_parameters(current_pending=700)
        assert interval_1 > 1.0  # Slowed down
        assert batch_1 < 500  # Decreased

        # Still shrinking: 700 → 300
        interval_2, batch_2 = sm.calculate_next_parameters(current_pending=300)
        assert interval_2 > interval_1
        assert batch_2 < batch_1

        # Empty: reset batch, cooldown interval
        interval_3, batch_3 = sm.calculate_next_parameters(current_pending=0)
        assert interval_3 > interval_2
        assert batch_3 == 100  # Reset to base

    def test_reset_clears_state(self) -> None:
        """Reset restores initial state."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)
        sm._previous_pending_count = 500
        sm._current_interval = 2.0
        sm._current_batch_size = 300

        sm.reset()

        # Use == instead of 'is' to avoid mypy unreachable false positive
        assert sm._previous_pending_count == None  # noqa: E711
        assert sm._current_interval == 5.0
        assert sm._current_batch_size == 100

    def test_stable_threshold_scales_with_backlog(self) -> None:
        """Stable threshold scales with current backlog depth."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)

        # High backlog: 2000 events
        sm._previous_pending_count = 2000
        sm._current_interval = 2.0  # Above minimum so scaling can be observed
        sm._current_batch_size = 500

        # delta = +10, stable_threshold = max(10, 2010 * 0.1) = 201
        # delta=10 < 201 → STABLE
        interval, batch = sm.calculate_next_parameters(current_pending=2010)
        assert interval == 2.0  # Maintained
        assert batch == 500  # Maintained

        # delta = +600, exceeds both stable threshold AND batch_size → GROWING_MODERATE
        sm._previous_pending_count = 2010
        sm._current_interval = 2.0
        sm._current_batch_size = 500

        interval_2, batch_2 = sm.calculate_next_parameters(current_pending=2610)
        # delta=600 > batch_size=500, stable_threshold=261
        assert interval_2 == pytest.approx(1.4)  # 2.0 * 0.7 (GROWING_MODERATE)
        assert batch_2 == 650  # 500 * 1.3 (GROWING_MODERATE)

    def test_uses_current_batch_for_thresholds(self) -> None:
        """Growth thresholds use current adaptive batch_size, not static base."""
        sm = AdaptiveOutboxStateMachine(base_interval=5.0, base_batch_size=100)

        # Batch has grown to 500
        sm._previous_pending_count = 1000
        sm._current_interval = 2.0  # Above minimum so scaling can be observed
        sm._current_batch_size = 500

        # delta = 150 (< 500, but > 115 stable threshold) → GROWING_SLOW (not MODERATE)
        # stable_threshold = max(10, 1150 * 0.1) = 115, delta=150 > 115
        interval, batch = sm.calculate_next_parameters(current_pending=1150)
        assert interval == pytest.approx(1.7)  # 2.0 * 0.85 (GROWING_SLOW)
        assert batch == pytest.approx(575, abs=1)  # 500 * 1.15 (GROWING_SLOW)

        # If we used static base=100 for thresholds, delta=150 > 100 would incorrectly
        # classify as GROWING_MODERATE instead of GROWING_SLOW
