# Script executor worker sample

Deploy the two warm worker pods with:

```bash
kubectl apply -k .
```

They use the public image names `quay.io/ahetheri/script-bash-executor:dev` and
`quay.io/ahetheri/script-python-executor:dev`. Both remain idle until a caller
starts `/usr/local/bin/script-executor --once` through `pods/exec`.

For example:

```bash
printf '%s\n' '{"code":"echo hello"}' | \
  kubectl -n syntara-script-executor-poc exec -i deployment/script-bash-executor-worker -- \
  /usr/local/bin/script-executor --once
```

The manifests deny all egress for both executor pods. This requires a cluster
network plugin that enforces Kubernetes NetworkPolicy; OpenShift does, while
the default local k3d Flannel network does not.
