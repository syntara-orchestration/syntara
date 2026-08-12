# Workflow Definition Guide

## Overview

This guide provides practical examples for defining V2 graph-based workflows with retry policies and error handling. Each example demonstrates real-world use cases and best practices for configuring retryable errors.

V2 workflows use a graph structure with `triggers`, `nodes`, and `edges` (replacing the V1 nested `workflow.activities` format). All field names use `snake_case`.

## Table of Contents

1. [API Integration with Rate Limiting](#api-integration-with-rate-limiting)
2. [Script Execution with Custom Exit Codes](#script-execution-with-custom-exit-codes)
3. [Multi-Service Workflow with Different Retry Strategies](#multi-service-workflow-with-different-retry-strategies)
4. [Using Default Retry Codes](#using-default-retry-codes)
5. [Advanced Error Handling Patterns](#advanced-error-handling-patterns)

## API Integration with Rate Limiting

**Use Case**: Calling a third-party API that implements rate limiting and may experience occasional server errors.

**Goals**:
- Automatically retry on rate limiting (429)
- Retry on transient server errors (5xx)
- Fail fast on auth errors (401, 403)
- Fail fast on not found (404) or validation errors (400, 422)

### Example Workflow

```yaml
schema_version: "2.0.0"
name: api-integration-with-rate-limiting
description: Fetch user data from third-party API with rate limiting

triggers:
  - id: trigger_manual
    type: manual_trigger
    config:
      inputs:
        userId:
          type: string
          description: User ID to fetch
          required: true
        apiToken:
          type: string
          description: API authentication token
          required: true

nodes:
  - id: fetch_user_data
    type: http_request
    name: Fetch User Data
    config:
      method: GET
      url: https://api.example.com/users/${trigger.userId}
      headers:
        Authorization: Bearer ${trigger.apiToken}
        Content-Type: application/json
    outputs:
      userData: $.body
    timeout: 30
    retry_policy:
      max_attempts: 5
      backoff: exponential
      initial_interval: 5
      max_interval: 300
      multiplier: 2.0
      retryable_errors:
        - 429
        - 500
        - 502
        - 503
        - 504

  - id: process_user_data
    type: script
    name: Process User Data
    config:
      language: python
      code: |
        import json
        import os

        user_data = json.loads(os.getenv('INPUT_USER_DATA', '{}'))

        processed = {
            "id": user_data.get("id"),
            "name": user_data.get("name"),
            "email": user_data.get("email"),
            "processed_at": "2026-01-15T00:00:00Z"
        }

        print(json.dumps(processed))
      inputs:
        user_data: ${fetch_user_data.output.userData}

edges:
  - from: trigger_manual
    to: fetch_user_data
  - from: fetch_user_data
    to: process_user_data
```

**Retry Behavior**:
- **429 error**: Retries with 5s → 10s → 20s → 40s → 80s (capped at 5m)
- **5xx errors**: Same retry pattern
- **401 error**: Fails immediately (auth issue)
- **404 error**: Fails immediately (user not found)
- **400 error**: Fails immediately (bad request)

**Key Points**:
- Exponential backoff prevents overwhelming the API during rate limits
- `max_interval` cap prevents excessive delays
- Only transient errors trigger retries
- Auth and validation errors fail fast

## Script Execution with Custom Exit Codes

**Use Case**: Running a bash script that checks external service availability and returns custom exit codes.

**Goals**:
- Retry on specific exit codes that indicate transient failures
- Fail fast on permanent errors
- Support custom exit codes for domain-specific logic

### Example Workflow

```yaml
schema_version: "2.0.0"
name: script-execution-custom-exit-codes
description: Health check script with custom retry logic

triggers:
  - id: trigger_manual
    type: manual_trigger
    config:
      inputs:
        serviceUrl:
          type: string
          description: URL of service to check
          default: "https://service.example.com/health"

nodes:
  - id: check_service_health
    type: script
    name: Check Service Health
    config:
      language: bash
      code: |
        #!/bin/bash

        # Exit codes:
        # 0 - Service healthy (success)
        # 1 - Service check failed permanently (e.g., invalid URL)
        # 2 - Service temporarily unavailable (retryable)
        # 3 - Upstream dependency down (retryable)

        SERVICE_URL="${INPUT_SERVICE_URL}"

        echo "Checking service health: $SERVICE_URL"

        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL" --max-time 10)

        if [ "$HTTP_CODE" -eq 200 ]; then
          echo "Service is healthy (HTTP 200)"
          exit 0
        elif [ "$HTTP_CODE" -eq 503 ]; then
          echo "Service temporarily unavailable (HTTP 503)"
          exit 2
        elif [ "$HTTP_CODE" -eq 502 ] || [ "$HTTP_CODE" -eq 504 ]; then
          echo "Upstream dependency issue (HTTP $HTTP_CODE)"
          exit 3
        elif [ "$HTTP_CODE" -eq 000 ]; then
          echo "Connection failed - check URL or network"
          exit 1
        else
          echo "Service returned HTTP $HTTP_CODE"
          exit 1
        fi
      inputs:
        service_url: ${trigger.serviceUrl}
    retry_policy:
      max_attempts: 3
      backoff: fixed
      initial_interval: 10
      retryable_errors:
        - 2
        - 3

  - id: alert_on_failure
    type: http_request
    name: Alert on Failure
    config:
      method: POST
      url: https://alerts.example.com/notify
      body:
        message: "Service health check failed"
        service: ${trigger.serviceUrl}

edges:
  - from: trigger_manual
    to: check_service_health
  - from: check_service_health
    to: alert_on_failure
```

**Retry Behavior**:
- **Exit code 2**: Retries with 10s → 10s → 10s intervals
- **Exit code 3**: Same retry pattern
- **Exit code 0**: Success (no retry)
- **Exit code 1**: Fails immediately (permanent error)

**Key Points**:
- Custom exit codes clearly document script behavior
- Fixed backoff is appropriate for known transient issues
- Only specific transient exit codes trigger retries
- Permanent errors (invalid config) fail fast

## Multi-Service Workflow with Different Retry Strategies

**Use Case**: Workflow that orchestrates multiple services, each with different reliability characteristics and retry requirements.

**Goals**:
- Critical services: aggressive retry with exponential backoff
- Optional services: limited retries
- Notification services: no retries (fail-fast)

### Example Workflow

```yaml
schema_version: "2.0.0"
name: multi-service-workflow
description: Process payment with multiple service dependencies

triggers:
  - id: trigger_manual
    type: manual_trigger
    config:
      inputs:
        orderId:
          type: string
          required: true
        amount:
          type: number
          required: true
        customerId:
          type: string
          required: true

nodes:
  # Critical: Payment processing - retry aggressively
  - id: process_payment
    type: http_request
    name: Process Payment
    config:
      method: POST
      url: https://payments.example.com/charge
      headers:
        Authorization: Bearer ${secrets.paymentApiKey}
      body:
        orderId: ${trigger.orderId}
        amount: ${trigger.amount}
        customerId: ${trigger.customerId}
    outputs:
      transactionId: $.body.transactionId
      status: $.body.status
    timeout: 30
    retry_policy:
      max_attempts: 10
      backoff: exponential
      initial_interval: 1
      max_interval: 600
      multiplier: 2.0
      retryable_errors:
        - 408
        - 429
        - 500
        - 502
        - 503
        - 504

  # Optional: Fraud detection - limited retries
  - id: fraud_check
    type: http_request
    name: Fraud Check
    config:
      method: POST
      url: https://fraud.example.com/check
      body:
        orderId: ${trigger.orderId}
        customerId: ${trigger.customerId}
        amount: ${trigger.amount}
    outputs:
      riskScore: $.body.riskScore
    timeout: 10
    retry_policy:
      max_attempts: 2
      backoff: fixed
      initial_interval: 5
      retryable_errors:
        - 503

  # Notification: Email - no retries to avoid duplicates
  - id: send_email
    type: http_request
    name: Send Email Notification
    config:
      method: POST
      url: https://email.example.com/send
      body:
        to: ${trigger.customerId}
        template: payment_confirmation
        data:
          orderId: ${trigger.orderId}
          transactionId: ${process_payment.output.transactionId}
    retry_policy:
      max_attempts: 1
      retryable_errors: []

edges:
  - from: trigger_manual
    to: process_payment
  - from: process_payment
    to: fraud_check
  - from: fraud_check
    to: send_email
```

**Retry Behavior by Service**:

| Service | Max Attempts | Strategy | Retryable Errors | Rationale |
|---------|-------------|----------|------------------|-----------|
| **process_payment** | 10 | Exponential | All transient (408, 429, 5xx) | Critical - must succeed |
| **fraud_check** | 2 | Fixed | 503 only | Optional - limited time budget |
| **send_email** | 1 | None | None | Idempotency concern |

**Key Points**:
- Different services have different criticality and retry needs
- Payment service: idempotency key allows safe retries
- Notification services: no retries to avoid duplicates
- Fraud check: limited retries to not delay payment

## Using Default Retry Codes

**Use Case**: Standard API integration with no special requirements.

**Goals**:
- Use sensible defaults for retry behavior
- Minimize configuration
- Follow industry best practices (Kubernetes patterns)

### Example Workflow

```yaml
schema_version: "2.0.0"
name: simple-api-integration
description: Fetch and update data from standard REST API

triggers:
  - id: trigger_manual
    type: manual_trigger
    config:
      inputs:
        resourceId:
          type: string
          required: true

nodes:
  - id: fetch_resource
    type: http_request
    name: Fetch Resource
    config:
      method: GET
      url: https://api.example.com/resources/${trigger.resourceId}
    outputs:
      resource: $.body
    retry_policy:
      max_attempts: 3
      backoff: exponential
      initial_interval: 1
      max_interval: 60
      # retryable_errors not specified - uses defaults: [408, 429, 500, 502, 503, 504]

  - id: update_resource
    type: http_request
    name: Update Resource
    config:
      method: PUT
      url: https://api.example.com/resources/${trigger.resourceId}
      body:
        status: processed
    outputs:
      updated: $.body
    retry_policy:
      max_attempts: 3
      backoff: exponential
      # retryable_errors not specified - uses defaults

edges:
  - from: trigger_manual
    to: fetch_resource
  - from: fetch_resource
    to: update_resource
```

**Retry Behavior** (using defaults `[408, 429, 500, 502, 503, 504]`):
- **408 (Request Timeout)**: Retries
- **429 (Too Many Requests)**: Retries
- **500 (Internal Server Error)**: Retries
- **502 (Bad Gateway)**: Retries
- **503 (Service Unavailable)**: Retries
- **504 (Gateway Timeout)**: Retries
- **4xx (except 408, 429)**: Fails immediately
- **Network errors without codes**: Fails immediately

**Key Points**:
- Defaults cover most common transient errors
- No need to specify `retryable_errors` for standard APIs
- Follows Kubernetes retry patterns
- Suitable for 80% of use cases

## Advanced Error Handling Patterns

### Pattern 1: Conditional Retry Based on Error Type

**Use Case**: Different retry strategies based on error code ranges.

```yaml
nodes:
  # Aggressive retry for server errors (5xx)
  - id: critical_operation
    type: http_request
    name: Critical Operation
    config:
      method: POST
      url: https://api.example.com/critical
    retry_policy:
      max_attempts: 5
      backoff: exponential
      retryable_errors:
        - 500
        - 501
        - 502
        - 503
        - 504
        - 505

  # Conservative retry for rate limiting only
  - id: rate_limited_operation
    type: http_request
    name: Rate Limited Operation
    config:
      method: GET
      url: https://api.example.com/rate-limited
    retry_policy:
      max_attempts: 10
      backoff: exponential
      initial_interval: 30
      max_interval: 1800
      retryable_errors:
        - 429
```

### Pattern 2: Sequential with Approval Gate

**Use Case**: Execute a task, then require human approval before proceeding.

```yaml
nodes:
  - id: prepare_data
    type: script
    name: Prepare Data
    config:
      language: python
      code: |
        import json
        print(json.dumps({"ready": True, "items": 42}))

  - id: review_gate
    type: approval
    name: Review Before Proceeding
    config:
      timeout: 3600

  - id: finalize
    type: script
    name: Finalize
    config:
      language: bash
      code: echo "Approved and finalized"

edges:
  - from: trigger_manual
    to: prepare_data
  - from: prepare_data
    to: review_gate
  - from: review_gate
    to: finalize
    from_port: approved
```

### Pattern 3: Script with Custom Exit Code Retry

**Use Case**: Process items with retry on specific failures.

```yaml
nodes:
  - id: process_item
    type: script
    name: Process Item
    config:
      language: bash
      code: |
        #!/bin/bash
        ITEM="${INPUT_ITEM}"

        # Exit codes:
        # 0 - Success
        # 1 - Permanent failure
        # 2 - Item locked (retryable)
        # 3 - Rate limit (retryable)

        if ! process_item "$ITEM"; then
          ERROR_CODE=$?
          if [ $ERROR_CODE -eq 2 ]; then
            echo "Item locked, will retry"
            exit 2
          elif [ $ERROR_CODE -eq 3 ]; then
            echo "Rate limit reached, will retry"
            exit 3
          else
            echo "Permanent failure"
            exit 1
          fi
        fi

        echo "Item processed successfully"
        exit 0
      inputs:
        item: ${trigger.item}
    retry_policy:
      max_attempts: 3
      retryable_errors:
        - 2
        - 3
```

## Best Practices Summary

### 1. Choose Appropriate Retry Counts

- **Critical operations**: 5-10 attempts
- **Standard operations**: 3-5 attempts
- **Optional operations**: 1-2 attempts
- **Non-idempotent operations**: 1 attempt (no retry)

### 2. Select Backoff Strategy

- **Exponential**: Default choice for most APIs (prevents overwhelming services)
- **Fixed**: Known recovery time or testing
- **Linear**: Gradual backoff without exponential growth

### 3. Configure max_interval

Always set `max_interval` to prevent unbounded delays:
- **Standard APIs**: 60 - 300 (1-5 minutes)
- **Rate-limited APIs**: 300 - 1800 (5-30 minutes)
- **Critical operations**: 600 - 3600 (10 minutes - 1 hour)

### 4. Customize retryable_errors When Needed

**Use defaults** (`[408, 429, 500, 502, 503, 504]`) unless:
- You need to retry only specific codes (e.g., only 429 for rate limiting)
- You're using custom exit codes in scripts
- You need strict fail-fast behavior (empty list)
- You know which errors are transient for your specific service

### 5. Document Custom Exit Codes

If using custom exit codes, document them in the script:

```yaml
config:
  code: |
    # Exit codes:
    # 0 - Success
    # 1 - Permanent failure
    # 2 - Temporary resource lock (retryable)
    # 3 - Rate limit (retryable)
```

### 6. Consider Idempotency

For non-idempotent operations:
- Add idempotency keys to API requests
- Or disable retries entirely (`max_attempts: 1`, `retryable_errors: []`)

### 7. Test Retry Behavior

Always test:
- Transient errors trigger retries
- Permanent errors fail fast
- Retry intervals match configuration
- `max_attempts` is respected

## Related Documentation

- [Workflow Engine Architecture](workflow-engine-overview.md) - How a saved definition becomes a running workflow
- [Retry Policies](retry-policies.md) - Detailed retry policy documentation
- [V2 Schema](../../src/syntara/schemas/workflows/v2/workflow_definition.schema.json) - V2 workflow definition JSON schema
- [Sample Workflows](../../samples/) - Working V2 workflow examples
