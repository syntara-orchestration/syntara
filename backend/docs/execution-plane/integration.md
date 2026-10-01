# Syntara and Execution Plane integration

Syntara remains the owner of user authentication, authorization, its public API facade, workflow dispatch, and OpenShift integration records. The versioned `execution-plane` Python package supplies worker, registry, model, and migration code. During this migration both applications use separate schemas in the same PostgreSQL database, and the EP worker completes Temporal activities directly.

The EP project documents the current crossings and the later service boundary in [its integration guide](https://github.com/syntara-orchestration/syntara-execution-plane/blob/cb46fd80908152b0ed57276ec0ae44fb96c420ea/docs/integration.md). Keep workflow dispatch, API authorization, migration isolation, and cluster synchronization changes coordinated across both repositories.
