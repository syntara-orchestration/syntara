# Receptor Kubernetes API bridge POC

This sample proves a single path: a control-side dispatcher reaches Kubernetes
`pods/exec` through a Receptor TCP bridge, sends one HTTP executor JSONL command
on stdin, and receives its JSONL result on stdout. It deliberately omits
Temporal and every Execution Plane scheduling or lifecycle service.

```mermaid
flowchart LR
  D[Dispatcher Job] -->|TLS API stream| H[Receptor hub :9443]
  H -->|Receptor mesh| B[Receptor bridge]
  B -->|raw TCP| K[Kubernetes API :443]
  K -->|pods/exec| W[Warm HTTP executor]
```

The dispatcher leaves its Kubernetes client host set to
`https://kubernetes.default.svc`. Its custom dialer connects the underlying TCP
socket only to `receptor-hub.syntara-control-poc.svc:9443`, preserving the API
TLS server name and certificate validation. Receptor only forwards bytes.

## Build images

The worker image is public at `quay.io/ahetheri/http-executor:dev`. Build and
push the dispatcher image before applying its Job:

```bash
cd backend/samples/execution-plane-receptor-kubeapi/dispatcher-poc
docker build -t quay.io/ahetheri/execution-plane-dispatcher-poc:dev -f Containerfile .
docker push quay.io/ahetheri/execution-plane-dispatcher-poc:dev
```

Replace the Job image in `dispatcher-poc.yaml` if a different registry or tag is
used. Add `--platform linux/amd64` when that is the architecture of the target
OpenShift nodes and the selected Docker builder supports cross-platform builds.
Receptor uses `quay.io/ansible/receptor:latest` for this short-lived POC;
replace it with a tested immutable digest before continued use.

## Run

Log in to the target OpenShift cluster, then run:

```bash
cd backend/samples/execution-plane-receptor-kubeapi
./smoke-test.sh
```

The script creates the two namespaces and base workloads, waits for them, then
runs the one-shot dispatcher Job. A successful job prints a wrapper object
whose `result` is the HTTP executor response, including `ok: true` and
`status_code: 200` for `https://example.com`.

To inspect the raw Kubernetes API bridge independently, run this from a pod
using the Dispatcher ServiceAccount:

```bash
curl --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  --header "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  --connect-to kubernetes.default.svc:443:receptor-hub.syntara-control-poc.svc:9443 \
  https://kubernetes.default.svc/api
```

`--connect-to` preserves the original Kubernetes hostname for HTTP and TLS but
dials the hub TCP door.

## Scope and constraints

The Dispatcher Role is isolated to the POC execution namespace and grants only
pod get/list and `pods/exec` create. Kubernetes RBAC cannot constrain those
verbs to a pod label, so this is a namespace boundary, not a production worker
authorization boundary. The dispatcher egress policy permits only DNS and the
hub door, ensuring it cannot directly dial the Kubernetes API or worker.

The bridge needs HTTPS egress to the API server. Standard NetworkPolicy cannot
select `kubernetes.default.svc` by name, so the sample permits TCP 443 and
documents the required API endpoint CIDR restriction for a real deployment.
The worker intentionally allows DNS and arbitrary HTTPS because the current
HTTP node requirement allows arbitrary internet destinations.

The next security increment is Receptor mesh TLS with a mounted CA and node
certificates. Kubernetes API TLS already stays end to end in this POC.
