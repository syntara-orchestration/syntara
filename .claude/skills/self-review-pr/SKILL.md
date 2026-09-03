---
description: "Adversarial self-review of your own PR before requesting external review. Catches data-flow leaks, sibling-path gaps, and broken test assertions."
user-invocable: true
---

# Self-Review PR

Run this before requesting review on any PR you authored. It simulates the review style that catches real issues — tracing code paths with specific inputs, not just reading the diff.

## Step 1: Identify the blast radius

```bash
gh pr diff <PR_NUMBER> --name-only
```

For each changed file, answer:
- What **reads** the values this file writes? (consumers)
- What **sibling** code paths do the same thing? (parity)
- What **tests** assert on the old behavior? (match strings)

## Step 2: Trace every consumer

For every value that changed (error messages, payload fields, function signatures, state propagation):

1. **grep for all consumers** of the old value — not just the one you fixed
2. For each consumer, ask: "Does this consumer still work with the new value?"
3. If you changed a message string, grep test files for `match=` or `assert.*in` on the old wording

Common misses:
- Fixing stream detail but missing failure signal payload (same `str(error)`)
- Fixing one strategy path (ALL) but missing sibling (SELECTED)
- Changing message format but not updating integration test `match=` strings
- Scrubbing error text in one channel but leaving it in DB columns exposed via API

## Step 3: Simulate scenarios

For each code path your PR touches, construct a specific input and trace it through every function:

- **Happy path**: Does it still work?
- **Error path**: Does the error propagate correctly? Is the error message client-safe?
- **Partial failure**: What if step 2 of 3 fails? Is cleanup correct?
- **Sibling path**: Does the sibling strategy/type/mode get the same fix?
- **Concurrency**: Can auto-submit/save fire between state updates? Use refs for synchronous guards, not state.

Write the scenarios as: "Input X → function A → function B → expected output Y". If you can't trace it mentally, read the code.

## Step 4: Check for over-scrubbing / under-scrubbing

When you restrict what reaches client-facing payloads:
- **Don't over-scrub**: Only scrub the specific exception types your PR introduces. Existing exceptions that operators rely on seeing should keep `str(e)`.
- **Don't under-scrub**: Check EVERY client-facing channel — stream events, failure signals, DB columns exposed via API, WebSocket messages, HTTP responses.

## Step 5: Verify test coverage

For each behavioral change:
1. Is there a test that would fail if the change were reverted?
2. Do existing tests still assert the right thing? (match strings, expected values)
3. Are integration tests updated too, not just unit tests?

## Step 6: Check for noise

- Did a formatter/linter change files unrelated to the PR? Revert them.
- Did contract regeneration touch example files? Revert those.
- Are there dead code wrappers that only exist for tests? Remove them; have tests import directly.

## Step 7: Lint and format

Run the full lint and format check on every changed file. CI will catch it, but fixing locally saves a round-trip:

```bash
# Backend
uv run ruff format --check src/
uv run ruff check src/

# Frontend
npx --prefix packages/syntara-ui eslint --flag v10_config_lookup_from_file <file>
```

Fix any issues, including pre-existing ones in files you touched (leave files no worse than you found them).

## Step 8: Final mental walkthrough

Read the full diff one more time and for each hunk ask:
- "What would Aaron say?" — Would a reviewer mentally executing this code with a specific edge-case input find a gap?
- "What breaks if I revert just this hunk?" — If the answer is "nothing", the hunk might be unnecessary noise.

Only after all 8 steps pass should you request review.
