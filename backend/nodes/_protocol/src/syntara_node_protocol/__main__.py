# ruff: noqa: T201 - command-line client output
"""Invoke a node's gRPC endpoint using an invocation JSON file."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path
from typing import Any

import grpc

from syntara_node_protocol.client import NodeRpcError, invoke
from syntara_node_protocol.codec import CHANNEL_OPTIONS, MAX_MESSAGE_BYTES, decode_object


def main() -> None:
    """Read a local file and send its contents as a protobuf request over gRPC."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="127.0.0.1:50051")
    parser.add_argument("--file", default="-", help="Invocation JSON file; '-' reads the client's stdin")
    parser.add_argument("--id", default="manual-invocation")
    parser.add_argument("--ca")
    parser.add_argument("--cert")
    parser.add_argument("--key")
    args = parser.parse_args()
    cancelled = threading.Event()

    def cancel(_signum: int, _frame: Any) -> None:  # noqa: ANN401
        cancelled.set()

    signal.signal(signal.SIGINT, cancel)
    signal.signal(signal.SIGTERM, cancel)
    if any((args.ca, args.cert, args.key)):
        if not all((args.ca, args.cert, args.key)):
            parser.error("TLS requires --ca, --cert and --key")
        credentials = grpc.ssl_channel_credentials(
            root_certificates=Path(args.ca).read_bytes(),
            private_key=Path(args.key).read_bytes(),
            certificate_chain=Path(args.cert).read_bytes(),
        )
        channel = grpc.secure_channel(args.address, credentials, options=CHANNEL_OPTIONS)
    else:
        if args.address.rsplit(":", 1)[0] not in {"localhost", "127.0.0.1", "[::1]"}:
            parser.error("Non-loopback connections require mutual TLS")
        channel = grpc.insecure_channel(args.address, options=CHANNEL_OPTIONS)
    try:
        raw = sys.stdin.buffer.read(MAX_MESSAGE_BYTES + 1) if args.file == "-" else Path(args.file).read_bytes()
        if len(raw) > MAX_MESSAGE_BYTES:
            parser.error("Invocation exceeds the message limit")
        with channel:
            result = invoke(
                channel,
                decode_object(raw),
                identity=args.id,
                progress=lambda event: print(json.dumps(event), flush=True),
                cancelled=cancelled,
            )
        print(json.dumps(result), flush=True)
    except (ValueError, TypeError, NodeRpcError):
        print("Node request failed; check the invocation and gRPC endpoint", file=sys.stderr)
        raise SystemExit(1) from None
    raise SystemExit(0 if result["result"]["StatusCode"] == 0 else 1)


if __name__ == "__main__":
    main()
