#!/usr/bin/env bash
set -euo pipefail

adapter="${1:-}"
if [[ "$adapter" != "http" && "$adapter" != "jetstream" && "$adapter" != "temporal" ]]; then
  echo "Usage: $0 {http|jetstream|temporal} [run_poc.py options]" >&2
  exit 2
fi
shift

cleanup() {
  if [[ -n "${container_name:-}" ]]; then
    docker rm --force "$container_name" >/dev/null 2>&1 || true
  fi
}

if [[ "$adapter" == "jetstream" && -z "${POC_NATS_URL:-}" ]]; then
  container_name="syntara-scheduler-wakeup-nats-$$"
  docker run --detach --rm --name "$container_name" -p 4222:4222 nats:2.10-alpine -js -sd /data >/dev/null
  trap cleanup EXIT
  export POC_NATS_URL="nats://127.0.0.1:4222"
  sleep 1
fi

if [[ "$adapter" == "jetstream" ]]; then
  PYTHONPATH=. uv run --extra jetstream python run_poc.py "$adapter" --nats-url "${POC_NATS_URL}" "$@"
else
  PYTHONPATH=. uv run python run_poc.py "$adapter" "$@"
fi
