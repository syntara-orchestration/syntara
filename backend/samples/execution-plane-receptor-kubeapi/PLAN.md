# Receptor Kubernetes API bridge POC plan

## Goal

Prove that Receptor TCP bridging can transport a Kubernetes API `pods/exec`
stream from a control-plane workload to a warm HTTP executor. The stream carries
one JSONL request on stdin and one JSONL result on stdout.

This is a sunny-day transport proof, not an Execution Plane implementation. It
does not include Temporal, a scheduler, task records, leases, retry, callbacks,
autoscaling, multi-cluster registration, or Workceptor.

## Data path

```mermaid
flowchart LR
  D[Dispatcher] -->|TLS request| H[Hub tcp-server :9443]
  H -->|Receptor mesh| B[Bridge tcp-client kubeapi]
  B -->|TCP| K[kubernetes.default.svc:443]
  K -->|pods/exec stdin/stdout| W[HTTP executor]
```

Receptor's current container uses its list-form configuration (`tcp-server`,
`tcp-client`, and `tcp-peer` entries). The hub accepts TCP on port 9443 and sends it to the named `kubeapi`
service on the execution-side bridge. The bridge opens the corresponding raw
TCP connection to `kubernetes.default.svc:443`. Receptor does not inspect or
terminate Kubernetes API TLS.

The Go dispatcher loads in-cluster client-go configuration, retains its API
host as `kubernetes.default.svc`, and sets `rest.Config.Dial` to the hub door.
That sends all Kubernetes TCP through Receptor while retaining the API server's
TLS SNI and hostname validation. It lists the one warm worker and invokes
`pods/exec` with `python -m syntara.http_executor`.

## Deliverables

- Control and execution namespaces.
- Hub and bridge Receptor deployments and their minimal TCP configurations.
- A warm `quay.io/ahetheri/http-executor:dev` pod whose normal entrypoint is
  held idle until exec starts it.
- A one-shot Go dispatcher Job and container image definition.
- Namespace-limited Dispatcher RBAC and POC NetworkPolicies.
- `smoke-test.sh`, which deploys the base, waits, runs the Job, and checks the
  returned executor result.

## Acceptance check

The dispatcher emits an HTTP executor result with `ok: true` and status 200
for `https://example.com`. The dispatcher egress policy permits only DNS and
the hub port, so it cannot directly connect to the Kubernetes API or worker.

## Follow-up after the proof

Add Receptor mesh TLS with mounted node certificates, pin container images by
digest, restrict bridge egress to the API endpoint CIDR, and add an
authorization layer because Kubernetes RBAC cannot limit `pods/exec` by pod
label.
