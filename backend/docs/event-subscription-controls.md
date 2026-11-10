# Kafka Subscribe connection testing

Kafka Subscribe exposes one workflow-scoped helper endpoint:

```text
POST /api/v1/workflows/{workflow_id}/event_subscriptions/test
```

The workflow builder's **Test connection** button sends unsaved Integration,
runtime credential and topic parameters to this endpoint. It checks connectivity
and topic metadata without publishing the workflow, starting an Execution,
joining a consumer group or committing offsets. Topic-read and consumer-group
permissions remain unverified by this non-consuming test.

The endpoint uses existing workflow permissions, with `workflow:update` required
at the route. Resource validation checks access to the Integration and runtime
credential. It does not introduce subscription-specific RBAC permissions or fall back to the
Integration's management credential.

Subscription configuration and activation use the existing workflow APIs.
There are no separate subscription list, detail, pause, resume, retry, manual
recovery or retirement endpoints. Publishing, unpublishing and listener changes
continue through the workflow lifecycle.

Publishing a subscription with a legacy pause flag clears that flag and advances
its configuration revision. Existing paused subscriptions remain stopped until
their workflows are republished; the upgrade does not resume them automatically.

The worker retains its internal placement, stop acknowledgements, delivery
claims, partition recovery fences and retirement safeguards. Offset gaps recover
automatically from retained beginning under the existing source, ownership and
delivery-evidence checks. Removing public operational controls does not remove
those safety boundaries or authorize deletion of unresolved work.

See [worker operations](kafka-worker-operations.md) and
[record runner recovery](kafka-record-runner.md) for runtime behavior and
retained-inspection safeguards.
