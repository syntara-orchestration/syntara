"""Compatibility shim — the nexus package has been renamed to syntara."""

import asyncio

from syntara.workflows.background_worker import main

if __name__ == "__main__":
    asyncio.run(main())
