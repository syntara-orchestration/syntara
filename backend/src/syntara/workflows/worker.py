"""Temporary compatibility entrypoint for the Temporal worker.

The operator currently identifies the worker by the legacy
``syntara.workflows.worker`` module name in its liveness probe. Keep this
shim until the operator recognizes ``syntara.workflow_runtime.workers.worker``;
then remove this module and update the container startup script.
"""

import asyncio

from syntara.workflow_runtime.workers.worker import main

if __name__ == "__main__":
    asyncio.run(main())
