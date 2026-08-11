"""Compatibility shim — the nexus package has been renamed to syntara."""

from syntara.api.main import (
    app,  # noqa: F401
    main,
)

if __name__ == "__main__":
    main()
