"""Register a kind ExecutionTarget using a ServiceAccount bearer token.

``ep-dev-up`` stores kubeconfig YAML as ``api_key``, which the vanilla-k8s
Bearer-token transport rejects. This helper writes the SA token instead.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from dev_cli import (
    EnvironmentDetails,
    EnvironmentProvider,
    _register_environment_record,
    resolve_database_url,
)

DEFAULT_CLUSTER = "execution-plane"
DEFAULT_ENDPOINT = "https://execution-plane-control-plane:6443"
DEFAULT_NAMESPACE = "execution-plane"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "token_file",
        type=Path,
        help="File containing the syntara-dispatcher ServiceAccount token.",
    )
    parser.add_argument("--cluster", default=DEFAULT_CLUSTER)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Read the token file and persist Cluster + default ExecutionTarget."""
    args = _build_parser().parse_args(argv)
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        print(f"Error: {args.token_file} is empty", file=sys.stderr)
        return 1
    details = EnvironmentDetails(
        provider=EnvironmentProvider.KIND,
        name=args.cluster,
        endpoint=args.endpoint,
        namespace=args.namespace,
        api_key=token,
        labels={"provider": EnvironmentProvider.KIND.value, "cluster": args.cluster},
    )
    database_url = resolve_database_url()
    asyncio.run(_register_environment_record(details, database_url))
    print("registered cluster + default target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
