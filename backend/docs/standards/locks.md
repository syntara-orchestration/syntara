# Thread Safety and Locks

## Overview

This document defines best practices for thread-safe programming and lock usage in Syntara. Python's Global Interpreter Lock (GIL) does not protect application-level data structures from race conditions, so explicit synchronization is required when shared state is accessed from multiple threads.

## When to Use Locks

Use locks when:

1. **Shared mutable state** - Multiple threads access the same mutable data structure
2. **State transitions** - Managing lifecycle states (e.g., `STOPPED ↔ RUNNING`)
3. **Counters and accumulators** - Updating shared numeric values
4. **Singleton initialization** - Ensuring single instance creation in concurrent environments
5. **Deduplication sets** - Tracking processed items across threads

## Lock Types

### threading.Lock (Preferred)

Standard non-reentrant lock. Use this by default.

```python
import threading

_state_lock = threading.Lock()
_state = "stopped"

def start() -> None:
    global _state
    with _state_lock:
        if _state == "running":
            return
        _state = "running"
        # ... initialization
```

**Characteristics:**
- Non-reentrant (same thread cannot acquire twice)
- Lightweight and fast
- Prevents deadlock from accidental re-acquisition

### threading.RLock (Special Cases)

Reentrant lock that allows the same thread to acquire multiple times.

**Only use when:**
- A locked function needs to call another locked function in the same class
- Recursive algorithms require the lock at each level

```python
import threading

class Cache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}

    def get_or_compute(self, key: str) -> Any:
        with self._lock:
            if key in self._data:
                return self._data[key]
            # Calls set() which also acquires the lock
            return self.set(key, self._compute(key))

    def set(self, key: str, value: Any) -> Any:
        with self._lock:  # RLock allows same thread to re-acquire
            self._data[key] = value
            return value
```

**Caution:** RLock is slower and can mask design issues. Prefer refactoring to avoid reentrant locks.

## Best Practices

### 1. Use Context Managers

Always use `with` statement for automatic release:

```python
# ✅ GOOD - Automatic release even on exception
with _lock:
    shared_state.update(value)

# ❌ BAD - Manual release error-prone
_lock.acquire()
try:
    shared_state.update(value)
finally:
    _lock.release()
```

### 2. Minimize Lock Scope

Lock only the critical section, not the entire function:

```python
# ✅ GOOD - Lock only protects shared state
def process_item(item: Item) -> None:
    result = expensive_computation(item)  # No lock needed

    with _results_lock:
        _results.append(result)  # Lock only shared state

# ❌ BAD - Holds lock during expensive computation
def process_item(item: Item) -> None:
    with _results_lock:
        result = expensive_computation(item)
        _results.append(result)
```

### 3. Avoid Nested Locks

Never acquire multiple locks without a clear ordering:

```python
# ❌ DANGEROUS - Can deadlock
with lock_a:
    with lock_b:
        # Thread 1: A → B
        # Thread 2: B → A (DEADLOCK!)
        shared_state.update()

# ✅ GOOD - Single lock for related state
_combined_lock = threading.Lock()

with _combined_lock:
    state_a.update()
    state_b.update()
```

**If multiple locks are unavoidable:**
- Document the lock ordering
- Always acquire in the same order across all code paths
- Consider using a single coarser-grained lock instead

### 4. Name Locks Descriptively

```python
# ✅ GOOD - Clear purpose
_state_lock = threading.Lock()
_workflow_completion_lock = threading.Lock()
_activity_success_lock = threading.Lock()

# ❌ BAD - Generic names
_lock = threading.Lock()
_lock1 = threading.Lock()
_lock2 = threading.Lock()
```

### 5. Document Thread Safety

Add docstring annotations for thread-safe functions and classes:

```python
def configure_otel_logging() -> None:
    """Configure OpenTelemetry logging for the audit logger.

    Thread-safe and idempotent - safe to call multiple times.
    Uses _otel_state_lock to prevent race conditions.
    """
    with _otel_state_lock:
        # ...
```

```python
class _BoundedDedup:
    """FIFO-bounded deduplication tracker.

    Thread-safe: All operations are protected by an internal lock to prevent
    race conditions during concurrent access from multiple threads.
    """
```

### 6. Protect All Access Paths

If state is protected by a lock, **all** access must use that lock:

```python
# ✅ GOOD - Consistent protection
_counters: list[int] = [0, 0]
_counter_lock = threading.Lock()

def increment() -> None:
    with _counter_lock:
        _counters[0] += 1

def get_rate() -> float:
    with _counter_lock:
        return _counters[0] / _counters[1]

# ❌ BAD - Inconsistent protection (race condition!)
def get_rate() -> float:
    return _counters[0] / _counters[1]  # No lock!
```

### 7. Use Atomic Operations Where Possible

For simple operations, consider lock-free approaches:

```python
from collections import deque

# ✅ GOOD - deque operations are atomic
_queue: deque[Item] = deque()
_queue.append(item)  # Thread-safe without lock

# But still need locks for non-atomic operations:
with _queue_lock:
    if len(_queue) > 0:  # Check and use requires lock
        item = _queue.popleft()
```

## Common Patterns

### Pattern 1: State Machine with Lock

Used in `audit/lifecycle.py` and `audit/otel_logging.py`:

```python
from enum import StrEnum
import threading

class ComponentState(StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"

_state_lock = threading.Lock()
_state = ComponentState.STOPPED

def start() -> None:
    """Start the component. Thread-safe and idempotent."""
    global _state

    with _state_lock:
        if _state == ComponentState.RUNNING:
            logger.debug("already_running")
            return

        # Initialization...
        _state = ComponentState.RUNNING

def stop() -> None:
    """Stop the component. Thread-safe and idempotent."""
    global _state

    with _state_lock:
        if _state == ComponentState.STOPPED:
            logger.debug("already_stopped")
            return

        # Cleanup...
        _state = ComponentState.STOPPED
```

### Pattern 2: Protected Counters

Used in `metrics/emission.py`:

```python
import threading

_counts: list[int] = [0, 0]  # [success, total]
_counts_lock = threading.Lock()

def record_result(success: bool) -> float:
    """Record result and return success rate."""
    with _counts_lock:
        _counts[1] += 1
        if success:
            _counts[0] += 1
        return _counts[0] / _counts[1]

def reset() -> None:
    """Reset counters."""
    with _counts_lock:
        _counts[:] = [0, 0]
```

### Pattern 3: Thread-Safe Singleton

Used in `auth/dependencies.py`:

```python
import threading
from typing import TypeVar, Callable

T = TypeVar("T")

_instance: T | None = None
_instance_lock = threading.Lock()

def get_singleton(factory: Callable[[], T]) -> T:
    """Get or create singleton instance (thread-safe)."""
    global _instance

    # Fast path: avoid lock if already initialized
    if _instance is not None:
        return _instance

    # Slow path: acquire lock and check again
    with _instance_lock:
        if _instance is None:
            _instance = factory()
        return _instance
```

**Double-checked locking:** Check before lock acquisition (fast path) and after (slow path).

### Pattern 4: Thread-Safe Collection Wrapper

Used in `metrics/emission.py`:

```python
import threading
from collections import OrderedDict
from typing import TypeVar

T = TypeVar("T")

class ThreadSafeSet:
    """Thread-safe set implementation with bounded size."""

    def __init__(self, max_size: int) -> None:
        self._data: OrderedDict[T, None] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def __contains__(self, item: T) -> bool:
        with self._lock:
            return item in self._data

    def add(self, item: T) -> None:
        with self._lock:
            self._data[item] = None
            while len(self._data) > self._max_size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
```

## Testing Thread Safety

### Test Idempotency

Verify functions can be called multiple times safely:

```python
def test_configure_is_idempotent():
    configure()
    initial_state = get_state()

    configure()  # Second call
    assert get_state() == initial_state

    configure()  # Third call
    assert get_state() == initial_state
```

### Test State Isolation

Use fixtures to reset state between tests:

```python
import pytest

@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None, None, None]:
    """Reset module state between tests."""
    import module_under_test

    with module_under_test._state_lock:
        module_under_test._state = InitialState

    yield

    with module_under_test._state_lock:
        module_under_test._state = InitialState
```

### Concurrent Access Testing

For critical paths, consider stress tests with multiple threads:

```python
import threading

def test_concurrent_access():
    results = []
    threads = []

    def worker():
        results.append(thread_safe_function())

    # Start 10 concurrent threads
    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    # Wait for completion
    for t in threads:
        t.join()

    # Verify no race conditions
    assert len(results) == 10
    assert all(r.is_valid() for r in results)
```

## Anti-Patterns to Avoid

### ❌ Lock Without Release Path

```python
# BAD - Exception causes lock to never release
_lock.acquire()
process()  # May raise exception
_lock.release()  # Never reached!
```

### ❌ Modifying Locked Value After Lock Release

```python
# BAD - Value accessed outside lock
with _lock:
    local_copy = shared_list.copy()
# shared_list may have changed here!
process(local_copy[0])  # May raise IndexError
```

### ❌ Long-Running Operations Under Lock

```python
# BAD - Network I/O while holding lock
with _lock:
    response = requests.get(url)  # Blocks other threads!
    _cache[key] = response
```

### ❌ Inconsistent Lock Usage

```python
# BAD - Some paths use lock, others don't
def set_value(v: int) -> None:
    with _lock:
        _value = v

def get_value() -> int:
    return _value  # No lock! Race condition!
```

## References

- **Audit lifecycle:** `src/syntara/audit/lifecycle.py` - State machine with lock
- **OTEL logging:** `src/syntara/audit/otel_logging.py` - State machine with lock  
- **Metrics emission:** `src/syntara/metrics/emission.py` - Protected counters and dedup set
- **Metrics store:** `src/syntara/metrics/store.py` - Thread-safe collection wrapper
- **Auth dependencies:** `src/syntara/auth/dependencies.py` - Thread-safe singleton

## See Also

- [Python threading documentation](https://docs.python.org/3/library/threading.html)
- [Python GIL explanation](https://wiki.python.org/moin/GlobalInterpreterLock)
- [Services](/docs/standards/services.md) - Service lifecycle patterns
