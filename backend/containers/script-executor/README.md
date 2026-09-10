# Syntara Script executor images

The Script executor is supplied as two separate stdin-driven OCI images:

| Image | Runtime | Included dependencies |
| --- | --- | --- |
| `quay.io/ahetheri/script-bash-executor:dev` | Bash | Bash only |
| `quay.io/ahetheri/script-python-executor:dev` | Python | Python standard library only |

Each image reads one JSON command per stdin line and writes one JSON result per
stdout line. The image chooses the runtime; callers cannot select an
interpreter in the request. A single invocation can process multiple lines.

Neither final image includes a package manager, `pip`, compiler, or a runtime
dependency installer. A script requiring a third-party Python package or an
external Unix utility requires a purpose-built executor image.

## Command interface

Every non-empty stdin line must be exactly one JSON object.

```json
{
  "code": "echo hello-$NAME",
  "environment": {"NAME": "Ada"},
  "timeout_seconds": 30
}
```

| Field | Required | Constraints |
| --- | --- | --- |
| `code` | Yes | Non-empty source code, up to 256 KiB. |
| `environment` | No | Up to 100 scalar values and 64 KiB in total. |
| `timeout_seconds` | No | Positive number, at most `SCRIPT_EXECUTOR_MAX_TIMEOUT_SECONDS`; defaults to 300 seconds. |

The runner builds a clean environment. It does not inherit the host's proxy
settings, credentials, or other variables. `PATH`, home and temporary-path
variables, loader variables (`LD_*` and `DYLD_*`), and Python runtime variables
cannot be supplied in `environment`.

The Bash image executes the code as:

```text
/bin/bash --noprofile --norc -c <code>
```

The Python image executes the code as:

```text
/usr/bin/python3 -I -B -c <code>
```

`-I` isolates Python from user site packages and Python environment variables;
`-B` prevents bytecode writes.

## Result interface

A successful Bash result looks like:

```json
{
  "ok": true,
  "return_code": 0,
  "stdout": "hello-Ada\\n",
  "stderr": "",
  "elapsed": 0.002
}
```

Python adds `stdout_json` when the complete stdout, or its last non-empty line,
is valid JSON:

```json
{
  "ok": true,
  "return_code": 0,
  "stdout": "debug\\n{\\"answer\\": 42}\\n",
  "stderr": "",
  "stdout_json": {"answer": 42},
  "elapsed": 0.03
}
```

Execution failures retain captured output and return `ok: false` with one of
`ValidationError`, `TimeoutError`, `ExecutionError`, or
`ScriptExecutionError`. Output is captured independently per stream and capped
at `SCRIPT_EXECUTOR_MAX_OUTPUT_BYTES`, which defaults to 1 MiB. Results include
`stdout_truncated` or `stderr_truncated` when a cap is reached.

## Run locally

Build both images from this directory:

```bash
docker build -f Containerfile.bash -t syntara-script-bash-executor:dev .
docker build -f Containerfile.python -t syntara-script-python-executor:dev .
```

Run a Bash command with a read-only filesystem and no network:

```bash
printf '%s\n' '{"code":"echo hello-$NAME","environment":{"NAME":"Ada"}}' | \
  docker run --rm -i --read-only --network none syntara-script-bash-executor:dev
```

Run a Python command with structured output:

```bash
printf '%s\n' '{"code":"import json; print(json.dumps({\"answer\": 42}))"}' | \
  docker run --rm -i --read-only --network none syntara-script-python-executor:dev
```

## Push to Quay

The following commands tag locally built images and publish them:

```bash
docker login quay.io
docker tag syntara-script-bash-executor:dev quay.io/ahetheri/script-bash-executor:dev
docker tag syntara-script-python-executor:dev quay.io/ahetheri/script-python-executor:dev
docker push quay.io/ahetheri/script-bash-executor:dev
docker push quay.io/ahetheri/script-python-executor:dev
```

Use `--platform linux/amd64` on the build command when that matches the target
OpenShift nodes and the Docker builder supports cross-platform builds.

## Run as warm OpenShift workers

The hardened worker sample is in
[`../../samples/script-executor`](../../samples/script-executor). It starts the
runner with `SCRIPT_EXECUTOR_KEEP_ALIVE=true`, allowing a later Kubernetes
`pods/exec` request to invoke a separate one-shot command:

```text
/usr/local/bin/script-executor --once
```

The sample disables ServiceAccount token mounting, uses a non-root UID,
read-only root filesystem, `RuntimeDefault` seccomp, dropped capabilities,
resource limits, and read-only mounts over `/tmp`, `/nonexistent`, and
`/dev/shm`. It applies deny-all egress to both workers.

The network policy needs a CNI that enforces Kubernetes NetworkPolicy. Standard
OpenShift OVN-Kubernetes does; the default local k3d Flannel setup does not.
