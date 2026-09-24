# Workflow Examples

This directory contains example YAML workflow files used for testing, demonstration, and documentation purposes.

## Directory Structure

- **`basic/`** - Core example workflows demonstrating fundamental features
  - `hello-world.yaml` - Simple sequential workflow with two bash script activities
  - `loop-demo.yaml` - forEach loop execution with default input values
  - `parallel-demo.yaml` - Parallel activity execution
  - `conditional-demo.yaml` - Conditional branching based on temperature input using nested condition activities
  - `retry-demo.yaml` - Retry policies with exponential and fixed backoff strategies

- **`loops/`** - Examples focused on loop constructs
  - `foreach-items.yaml` - forEach loop with item processing and default values

- **`parallel/`** - Examples focused on parallel execution
  - `parallel-tasks.yaml` - Three parallel tasks executing concurrently

- **`error-handling/`** - Examples demonstrating error handling patterns
  - `failing-task.yaml` - Task with expected failure and retry policy
  - `transient-errors.yaml` - Retry on transient failures with exponential backoff
  - `error-propagation.yaml` - How errors propagate through sequential activities

- **`timeout-retry/`** - Examples focused on timeout and retry scenarios
  - `activity-timeout.yaml` - Activity with timeout configuration
  - `retry-policy.yaml` - Retry policy with exponential backoff
  - `timeout-with-retry.yaml` - Combined timeout and retry policies

- **`parameters/`** - Examples showing parameter mapping patterns
  - `activity-chaining.yaml` - Output-to-input parameter mapping between activities
  - `input-expressions.yaml` - Various input parameter expression formats

## Usage

### Via CLI Tool

Run workflows using the CLI tool:

```bash
# Basic examples
python tools/workflow_cli.py run tests/integration/workflow/examples/basic/hello-world.yaml

# Loop demo with custom inputs
python tools/workflow_cli.py run tests/integration/workflow/examples/basic/loop-demo.yaml \
  --inputs '{"items": ["apple", "banana", "cherry"]}'

# Loop demo with default inputs
python tools/workflow_cli.py run tests/integration/workflow/examples/basic/loop-demo.yaml

# Parallel execution
python tools/workflow_cli.py run tests/integration/workflow/examples/basic/parallel-demo.yaml

# Conditional logic examples
python tools/workflow_cli.py run tests/integration/workflow/examples/basic/conditional-demo.yaml \
  --inputs '{"temperature": 35}'   # Hot weather

python tools/workflow_cli.py run tests/integration/workflow/examples/basic/conditional-demo.yaml \
  --inputs '{"temperature": 10}'   # Cold weather

python tools/workflow_cli.py run tests/integration/workflow/examples/basic/conditional-demo.yaml \
  --inputs '{"temperature": 22}'   # Mild weather

# Retry policies
python tools/workflow_cli.py run tests/integration/workflow/examples/basic/retry-demo.yaml \
  --inputs '{"failure_rate": 30}'  # Easier to succeed (30% chance of failure)

python tools/workflow_cli.py run tests/integration/workflow/examples/basic/retry-demo.yaml \
  --inputs '{"failure_rate": 90}'  # Harder to succeed (90% chance of failure, will retry)

# Error handling examples
python tools/workflow_cli.py run tests/integration/workflow/examples/error-handling/failing-task.yaml

python tools/workflow_cli.py run tests/integration/workflow/examples/error-handling/transient-errors.yaml

# Loop examples
python tools/workflow_cli.py run tests/integration/workflow/examples/loops/foreach-items.yaml

python tools/workflow_cli.py run tests/integration/workflow/examples/loops/foreach-items.yaml \
  --inputs '{"item_list": ["custom1", "custom2", "custom3"]}'

# Parameter mapping examples
python tools/workflow_cli.py run tests/integration/workflow/examples/parameters/activity-chaining.yaml

# Timeout and retry examples
python tools/workflow_cli.py run tests/integration/workflow/examples/timeout-retry/retry-policy.yaml

python tools/workflow_cli.py run tests/integration/workflow/examples/timeout-retry/timeout-with-retry.yaml
```

### Via Integration Tests

These workflows are used by the integration test suite in `tests/integration/workflow/`. Each example is:

- Validated against the JSON schema (`v2/workflow_definition.schema.json`)
- Tested end-to-end through Temporal
- Verified for correct output and behavior

See the test files for programmatic usage examples.

## Schema Validation

All examples are validated against `schemas/workflows/v2/workflow_definition.schema.json`.

Run validation tests:

```bash
# Validate all examples against schema
pytest tests/integration/workflow/test_example_schema_validation.py -v

# Run specific example tests
pytest tests/integration/workflow/test_example_schema_validation.py::test_example_schema_validation -v
```

## Requirements

- Temporal dev server running on `localhost:7233`
- Start with: `temporal server start-dev`

## Adding New Examples

When adding new examples:

1. Place them in the appropriate category directory
2. Ensure they validate against the schema
3. Add integration tests to verify they work end-to-end
4. Update this README with usage examples
5. Add to `test_example_schema_validation.py` parametrized test
