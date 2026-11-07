"""Temporary compatibility entrypoint for the background Temporal worker.

The operator currently identifies the worker by the legacy
``syntara.workflows.background_worker`` module name in its liveness probe.
Keep this shim until the operator recognizes
``syntara.workflow_runtime.workers.background_worker``; then remove this
module and update the container startup script.
"""

import asyncio

from syntara.workflow_runtime.workers.background_worker import main

if __name__ == "__main__":
    asyncio.run(main())
