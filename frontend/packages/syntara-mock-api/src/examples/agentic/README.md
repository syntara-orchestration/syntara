# Agentic Workflow Examples

This directory contains example workflows that demonstrate the agentic activity executor, which integrates with the Agent Orchestrator service to execute AI-driven tasks within workflows.

## Overview

Agentic activities allow workflows to leverage AI agents for complex reasoning, research, analysis, and decision-making tasks. Each agentic task can:

- Use specialized AI models (e.g., Claude 3.5 Sonnet)
- Process complex prompts with template variables
- Stream progress updates via WebSocket
- Handle errors and retries gracefully

## Example Workflows

### 1. simple-research.yaml

**Description**: Basic agentic workflow that performs web research on a topic.

**Use Case**: Quick research and summarization

**Key Features**:
- Single agentic task
- Template variable substitution (`{{input.topic}}`)
- Output mapping for structured results

**Manual Testing**:
```bash
# Execute with custom input
curl -X POST http://localhost:8000/api/v1/workflows/executions \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "simple-research",
    "inputs": {
      "research_topic": "quantum computing advances in 2024"
    }
  }'
```

---

### 2. hybrid-workflow.yaml

**Description**: Combines script tasks and agentic tasks in a single workflow.

**Use Case**: Data preparation, AI analysis, and report generation

**Key Features**:
- Mixed executor types (script + agentic)
- Data flow between activities
- Output chaining (`{{activities.prepare_data.output.status}}`)

**Manual Testing**:
```bash
curl -X POST http://localhost:8000/api/v1/workflows/executions \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "hybrid-workflow",
    "inputs": {}
  }'
```

---

### 3. multi-agent-pipeline.yaml

**Description**: Sequential pipeline with specialized agents for research, analysis, and strategy.

**Use Case**: Comprehensive analysis requiring multiple specialized AI agents

**Key Features**:
- Multiple agentic tasks in sequence
- Different specialized agents for each phase
- Progressive data enrichment
- Cross-activity output references

**Manual Testing**:
```bash
curl -X POST http://localhost:8000/api/v1/workflows/executions \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "multi-agent-pipeline",
    "inputs": {
      "topic": "artificial intelligence regulation in healthcare"
    }
  }'
```

---

### 4. parallel-research.yaml

**Description**: Parallel agentic tasks for comprehensive multi-domain research.

**Use Case**: Concurrent research across technical, market, and regulatory domains

**Key Features**:
- Parallel execution of agentic tasks
- Different specialized agents per branch
- Final synthesis step combining all results
- Demonstrates workflow concurrency

**Manual Testing**:
```bash
curl -X POST http://localhost:8000/api/v1/workflows/executions \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "parallel-research",
    "inputs": {
      "topic": "renewable energy storage solutions"
    }
  }'
```

---

### 5. conditional-agent-routing.yaml

**Description**: Dynamically route requests to specialized agents based on classification.

**Use Case**: Intelligent request routing to domain experts

**Key Features**:
- AI-powered classification
- Conditional execution based on agent output
- Dynamic agent selection
- Demonstrates decision-making workflows

**Manual Testing**:
```bash
# Technical request
curl -X POST http://localhost:8000/api/v1/workflows/executions \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "conditional-agent-routing",
    "inputs": {
      "user_request": "How do I optimize database query performance?"
    }
  }'

# Business request
curl -X POST http://localhost:8000/api/v1/workflows/executions \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "conditional-agent-routing",
    "inputs": {
      "user_request": "What market entry strategy should we consider for Asia?"
    }
  }'
```

---

## Agentic Task Configuration

All agentic tasks use the following configuration structure:

```yaml
task:
  executor: agentic
  parameters:
    agent: production://agent-name        # Agent routing identifier
    model: claude-3-5-sonnet-20241022     # AI model to use
    prompt: |                              # Natural language prompt
      Task description with {{variables}}
  inputs:                                  # Runtime input mapping
    key: "{{expression}}"
  outputs:                                 # Output extraction
    key: $.result.field
```

## Agent Orchestrator Integration

Agentic activities connect to the Agent Orchestrator service via:

- **HTTP API**: For invoking agents (`POST /invoke`)
- **WebSocket**: For streaming progress updates (`/ws/invoke/{invocation_id}`)

## Monitoring Execution

Monitor agentic workflow execution:

```bash
# Get execution status
curl http://localhost:8000/api/v1/workflows/executions/{execution_id}

# Stream execution events (WebSocket)
wscat -c ws://localhost:8000/api/v1/workflows/executions/{execution_id}/events
```

## Error Handling

Agentic activities include robust error handling for:

- **Agent Unavailable**: Retries with exponential backoff
- **Timeout**: Configurable timeouts per activity
- **Agent Errors**: Captures and maps Agent Orchestrator errors

Example with retry policy:

```yaml
task:
  executor: agentic
  parameters:
    # ... parameters
  timeout: PT5M                  # 5 minute timeout
  retryPolicy:
    maxAttempts: 3
    initialInterval: PT1S
    maxInterval: PT10S
    backoff: exponential
```

## Development Tips

1. **Start Simple**: Begin with `simple-research.yaml` to understand basic agentic tasks
2. **Monitor Logs**: Check Agent Orchestrator logs for detailed execution traces
3. **Use Variables**: Leverage template variables for dynamic prompts
4. **Chain Outputs**: Build complex workflows by chaining activity outputs

## Related Documentation

- [Agentic Activity Implementation](../../../../../src/syntara/workflows/activities/agentic_activity.py)
