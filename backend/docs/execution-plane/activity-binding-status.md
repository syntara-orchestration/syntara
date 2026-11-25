# ExecutionPlaneActivityBinding status

`ExecutionPlaneActivityBinding.status` is AO's durable state machine for
connecting one Temporal activity attempt to one idempotent Execution Plane
request. The binding records dispatch handoff and completion delivery; it does
not mirror the EP WorkItem state.

## Sequence

```mermaid
sequenceDiagram
    autonumber
    participant T as Temporal activity
    participant B as AO bridge
    participant EP as Execution Plane
    participant C as EP callback
    participant R as Completion worker

    T->>B: persist_dispatch_binding(request_id)
    B->>B: status = submitting
    T->>EP: submit work item(request_id, frozen payload)

    alt EP unavailable
        EP-->>T: unavailable / timeout
        T->>EP: retry same request_id
        Note over B,EP: Binding remains submitting
    else EP accepts non-terminal work
        EP-->>T: pending/claimed/dispatched/etc.
        T->>B: mark_dispatch_accepted(terminal=false)
        B->>B: status = handoff_pending
        EP-->>C: authenticated completion event
        C->>B: persist_completion_event()
        B-->>C: 202 Accepted
        R->>B: claim event and binding
        B->>B: status = delivering
        R->>T: complete Temporal activity with result
        alt Temporal completion succeeds
            R->>B: mark event processed
            B->>B: status = completed
        else completion outcome is uncertain
            R->>B: mark event for reconciliation
            B->>B: status = reconciliation_required
        end
    else EP returns terminal state
        EP-->>T: completed / failed / cancelled
        T->>B: mark_dispatch_accepted(terminal=true)
        B->>B: status = completed_synchronously
        Note over T,B: Terminal response is returned directly;
        Note over T,B: callback delivery is treated as already processed.
    end

    opt callback is missing
        B->>EP: status lookup for handoff_pending binding
        EP-->>B: terminal WorkItem state
        B->>B: persist recovered completion event
        B->>B: status = delivering
        B->>T: complete activity or require reconciliation
    end
```

## State machine

```mermaid
stateDiagram-v2
    [*] --> submitting: persist dispatch binding

    submitting --> submitting: EP unavailable, retry same request_id
    submitting --> handoff_pending: EP accepts non-terminal work
    submitting --> completed_synchronously: EP returns terminal state

    handoff_pending --> delivering: callback or status reconciliation claimed
    handoff_pending --> handoff_pending: callback not ready / status still non-terminal

    delivering --> completed: Temporal completion succeeds
    delivering --> reconciliation_required: completion outcome uncertain

    reconciliation_required --> reconciliation_required: preserve EP result for operator reconciliation

    completed_synchronously --> [*]
    completed --> [*]
    reconciliation_required --> [*]
```

`reconciliation_required` is intentionally terminal from the worker's point
of view: AO must not risk completing the Temporal activity twice when the
previous completion outcome is unknown.
