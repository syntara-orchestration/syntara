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

See [how Receptor bridges the Kubernetes API](receptor_bridging_kube.md) for a
step-by-step request and response trace.

## OpenShift deployment

The worker image is public at `quay.io/ahetheri/http-executor:dev`. Build and
push the Dispatcher image before applying its Job:

```bash
cd backend/samples/execution-plane-receptor-kubeapi/dispatcher-poc
docker login quay.io
docker build -t quay.io/ahetheri/execution-plane-dispatcher-poc:dev -f Containerfile .
docker push quay.io/ahetheri/execution-plane-dispatcher-poc:dev
```

Replace the Job image in `dispatcher-poc.yaml` if a different registry or tag is
used. Add `--platform linux/amd64` when that is the architecture of the target
OpenShift nodes and the selected Docker builder supports cross-platform builds.
Receptor uses `quay.io/ansible/receptor:latest` for this short-lived POC;
replace it with a tested immutable digest before continued use.

Log in to the target cluster and confirm the active identity before deploying:

```bash
oc whoami
oc cluster-info
```

### Automated smoke test

The script deploys the base workloads, waits for the Receptor mesh and warm
worker, creates the Dispatcher Job, and verifies the returned HTTP result.

```bash
cd backend/samples/execution-plane-receptor-kubeapi
./smoke-test.sh
```

The script creates the two namespaces and base workloads, waits for them, then
runs the one-shot dispatcher Job. A successful job prints a wrapper object
whose `result` is the HTTP executor response, including `ok: true` and
`status_code: 200` for `https://example.com`.

### Manual deployment and test

Use this when you want to observe each stage separately:

```bash
cd backend/samples/execution-plane-receptor-kubeapi

oc apply -k .
oc -n syntara-control-poc rollout status deployment/receptor-hub --timeout=120s
oc -n syntara-execution-poc rollout status deployment/receptor-bridge --timeout=120s
oc -n syntara-execution-poc rollout status deployment/http-executor-worker --timeout=120s

oc -n syntara-control-poc delete job/dispatcher-poc --ignore-not-found
oc apply -f dispatcher-poc.yaml
oc -n syntara-control-poc wait --for=condition=complete job/dispatcher-poc --timeout=120s
oc -n syntara-control-poc logs job/dispatcher-poc
```

The final log line is a JSON object with `ok: true`, a nested executor result,
and `status_code: 200`. Observe the byte bridge while the Job runs with:

```bash
oc -n syntara-control-poc logs --follow deployment/receptor-hub
oc -n syntara-execution-poc logs --follow deployment/receptor-bridge
```

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

## Local Kubernetes deployment and manual test

This repository has been verified on the local `k3d-execution-plan-poc` cluster
using Rancher Desktop's Docker context. The local flow imports native local
images into k3d, rather than requiring a registry push.

Build the two images from the repository root:

```bash
cd /Users/ahetheri/syntara_workarea/syntara-http-executor

docker build -f backend/containers/http-executor/Containerfile \
  -t syntara-http-executor:dev backend

docker build \
  -f backend/samples/execution-plane-receptor-kubeapi/dispatcher-poc/Containerfile \
  -t execution-plane-dispatcher-poc:dev \
  backend/samples/execution-plane-receptor-kubeapi/dispatcher-poc
```

For the existing `execution-plan-poc` cluster, load the images directly into
its k3s container:

```bash
docker save syntara-http-executor:dev execution-plane-dispatcher-poc:dev | \
  docker exec -i k3d-execution-plan-poc-server-0 ctr -n k8s.io images import -
```

Apply the base components with local image names, then wait for the mesh and
warm worker. The Job is intentionally not part of `kustomization.yaml`, so it
cannot run before these components are ready.

```bash
cd backend/samples/execution-plane-receptor-kubeapi

kubectl kustomize . | \
  sed \
    -e 's#quay.io/ahetheri/http-executor:dev#syntara-http-executor:dev#' \
    -e 's/imagePullPolicy: Always/imagePullPolicy: IfNotPresent/g' | \
  kubectl apply -f -

kubectl -n syntara-control-poc rollout status deployment/receptor-hub --timeout=120s
kubectl -n syntara-execution-poc rollout status deployment/receptor-bridge --timeout=120s
kubectl -n syntara-execution-poc rollout status deployment/http-executor-worker --timeout=120s
```

Create the local Dispatcher Job and view its result:

```bash
kubectl -n syntara-control-poc delete job/dispatcher-poc --ignore-not-found

sed \
  -e 's#quay.io/ahetheri/execution-plane-dispatcher-poc:dev#execution-plane-dispatcher-poc:dev#' \
  -e 's/imagePullPolicy: Always/imagePullPolicy: IfNotPresent/' \
  dispatcher-poc.yaml | kubectl apply -f -

kubectl -n syntara-control-poc wait --for=condition=complete job/dispatcher-poc --timeout=120s
kubectl -n syntara-control-poc logs job/dispatcher-poc
```

Clean up either environment when finished:

```bash
kubectl delete namespace syntara-control-poc syntara-execution-poc
```

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
