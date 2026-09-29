# agent SDK node

This folder produces `syntara-node-agent`. Its entrypoint starts a gRPC server
on port 50051. See [the runtime and deployment guide](../README.md) for the protobuf
contract, port-forwarding, mutual TLS, cancellation and workflow compatibility.

From the repository root:

```bash
make node-image NODE=agent REGISTRY=quay.io/your-organization TAG=grpc-migration
```

With a running pod and its gRPC port forwarded to localhost:

```bash
uv run --project backend --no-sync python -m syntara_node_protocol \
  --address 127.0.0.1:50051 --file backend/nodes/agent/example.json
```

Set real URLs and reference IDs in a protected copy of `example.json`; never commit
credentials. The client sends protobuf requests and receives a gRPC response stream.
The pod accepts one invocation and exits after returning its result. Logs go to
stderr. Agent dispatch returns an acknowledgement; its existing AO callback owns
workflow completion.

Build this folder's `Containerfile` with **backend/nodes as the build context**.
