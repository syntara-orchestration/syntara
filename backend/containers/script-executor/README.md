# Syntara script executors

Two separate stdin-driven images execute workflow script-node code:

- `script-bash-executor` runs Bash code with `/bin/bash`.
- `script-python-executor` runs Python code with the Python standard library.

Neither final image contains a package manager, `pip`, compiler, or runtime
dependency installer. The Bash image has Bash only; scripts requiring external
Unix utilities need a purpose-built image. Network access is not provided by
the OpenShift worker manifest.

Each image reads one JSON object per stdin line and emits one JSON object per
stdout line. The runtime is selected by the image, not by the input.

```console
printf '%s\n' '{"code":"echo hello-$NAME","environment":{"NAME":"Ada"}}' | \
  docker run --rm -i --read-only --network none syntara-script-bash-executor:dev
```

```console
printf '%s\n' '{"code":"import json; print(json.dumps({\"answer\": 42}))"}' | \
  docker run --rm -i --read-only --network none syntara-script-python-executor:dev
```

The command fields are:

- `code` — required, non-empty script source, up to 256 KiB.
- `environment` — optional object of up to 100 scalar values and 64 KiB total.
- `timeout_seconds` — optional positive number; at most the image's configured
  `SCRIPT_EXECUTOR_MAX_TIMEOUT_SECONDS`, which defaults to 300 seconds.

`PATH`, home and temporary-directory variables, loader variables, and Python
runtime variables cannot be supplied through `environment`. The executor
creates a clean environment and does not inherit host credentials or proxies.

Success results contain `return_code`, `stdout`, `stderr`, and `elapsed`.
Python success results also contain `stdout_json` when all stdout, or its final
non-empty line, is valid JSON. Failures return `ok: false` and an `error_type`.
Both output streams are independently capped by
`SCRIPT_EXECUTOR_MAX_OUTPUT_BYTES` (1 MiB by default).

Build the images from `backend/containers/script-executor`:

```bash
docker build -f Containerfile.bash -t quay.io/ahetheri/script-bash-executor:dev .
docker build -f Containerfile.python -t quay.io/ahetheri/script-python-executor:dev .
```

Push them after authenticating to Quay:

```bash
docker login quay.io
docker push quay.io/ahetheri/script-bash-executor:dev
docker push quay.io/ahetheri/script-python-executor:dev
```

The hardened warm-worker example is at
[`../../samples/script-executor`](../../samples/script-executor). It enables
the runner's idle mode so a later Kubernetes `pods/exec` call can start a
separate executor process with `/usr/local/bin/script-executor --once`. It disables ServiceAccount token mounting, masks
common temporary paths read-only, sets a read-only root filesystem and runtime
seccomp profile, drops capabilities, and applies default-deny egress.

NetworkPolicy needs a network plugin that enforces NetworkPolicy. OpenShift's
standard networking does; the default k3d Flannel setup used for local testing
does not, so do not treat a local k3d run as evidence that egress is blocked.
