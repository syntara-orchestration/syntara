"""Bridge gRPC's TCP channel to the Kubernetes client's forwarded socket."""

from __future__ import annotations

import select
import socket
import threading
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def forward_socket(remote: socket.socket) -> Iterator[str]:
    """Forward raw HTTP/2 bytes over one connection, without interpreting requests."""
    stopped = threading.Event()
    local_connections: list[socket.socket] = []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.2)

        def pump() -> None:
            try:
                while not stopped.is_set():
                    try:
                        local, _address = listener.accept()
                        break
                    except TimeoutError:
                        continue
                else:
                    return
                with local:
                    local_connections.append(local)
                    local.settimeout(2)
                    remote.settimeout(2)
                    while not stopped.is_set():
                        readable, _, _ = select.select([local, remote], [], [], 0.2)
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                return
                            destination = remote if source is local else local
                            destination.sendall(data)
            except (OSError, ValueError):
                # gRPC reports the broken channel without raw API diagnostics.
                return

        thread = threading.Thread(target=pump, daemon=True, name="node-grpc-port-forward")
        thread.start()
        try:
            yield f"127.0.0.1:{listener.getsockname()[1]}"
        finally:
            stopped.set()
            for connection in [*local_connections, remote]:
                with suppress(OSError):
                    connection.shutdown(socket.SHUT_RDWR)
                connection.close()
            thread.join(timeout=3)
