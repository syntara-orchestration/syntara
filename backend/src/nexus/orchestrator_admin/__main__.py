"""Compatibility shim — the nexus package has been renamed to syntara."""

from syntara.orchestrator_admin.__main__ import main

if __name__ == "__main__":
    main()
