"""Entry point for credential CLI tools.

Usage: uv run python -m syntara.credentials.cli rotate-keys [options]
"""

from syntara.credentials.cli.rotate_keys import main

if __name__ == "__main__":
    main()
