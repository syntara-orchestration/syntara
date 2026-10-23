# Disposable local Kafka example

This opt-in fixture uses the [Apache Kafka image](https://kafka.apache.org/39/getting-started/docker/)
and a single KRaft broker with SASL/PLAIN over TLS. It is local development data,
not customer infrastructure or a broker/TLS certification matrix. The fixed
`fixture` / `disposable-local-only` identity is only for this disposable broker.
No customer secrets or Kafka resources are seeded by application setup.

The current worker requires `SASL_SSL`. This minimal fixture therefore uses TLS
so the worker can connect to it, differing from the design's plaintext quick-start
note. Live broker/TLS verification matrices remain deferred. `server.properties`
configures only this disposable broker; customer brokers keep their own configuration.

Run the following from the repository root, after the normal `make setup` has
prepared the local database, migrations, keys, certificates and backend image:

```bash
# Include a Kafka certificate under the existing disposable development CA.
uv run --project backend python backend/tools/generate_certs.py --kafka
uv run --project backend podman-compose --profile kafka up -d kafka

# Explicitly create a disposable topic; the broker disables automatic creation.
uv run --project backend podman-compose --profile kafka exec kafka \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 \
  --command-config /fixture/client.properties --create --if-not-exists \
  --topic syntara-fixture --partitions 1 --replication-factor 1
```

The broker advertises `kafka:9092` to compose clients and `localhost:9093` to host
clients. Only the host listener is published, bound to `127.0.0.1`. Broker logs and
KRaft state live in tmpfs and disappear when the container is removed. The generated
local certificate/key files remain under ignored `backend/.secrets/certs/`.
Creating this single-partition example topic is a manual local setup step.
Customer administrators retain control of their topics and partition counts.

Explicitly allow the disposable broker hostname on the local API before creating
the Integration. The default allowlist remains unchanged. Retain any other
hostnames your local setup already needs:

```bash
APP_INTEGRATION_URL_ALLOWED_HOSTS='["mcp-server","kafka"]' \
  uv run --project backend podman-compose up -d syntara
```

Use `integration.example.json` as the Integration create-body template:

1. Replace `configuration.ca_certificate` with the PEM contents of
   `backend/.secrets/certs/ca.pem`. Keep certificate verification enabled.
2. For a host-run API/worker, use `localhost:9093` and allow `localhost` through
   `APP_INTEGRATION_URL_ALLOWED_HOSTS` on both processes. For compose, the commands
   here explicitly allow the exact `kafka` hostname. Customer deployments use
   their own broker allowlist and network rules.
3. Create a local Kafka Credential through the normal API/UI with username
   `fixture` and password `disposable-local-only`. Link it as the management
   credential for preflight and select it as the workflow listener's runtime
   credential. The example does not call the API or create credentials itself.
4. Publish a workflow with a Kafka Subscribe listener on exact topic
   `syntara-fixture`, using that Integration and runtime Credential. Leave its
   generated consumer-group identity and initial boundary under application control.

Enable the independent worker explicitly; the flag remains false by default:

```bash
APP_INTEGRATION_URL_ALLOWED_HOSTS='["mcp-server","kafka"]' \
  make -C backend eventstream-consumer-run

cat backend/samples/kafka/event.example.json | \
  uv run --project backend podman-compose --profile kafka exec -T kafka \
  /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:9092 \
  --producer.config /fixture/client.properties --topic syntara-fixture
```

The worker depends on PostgreSQL and Temporal, with existing development signing,
encryption and mTLS files. Redis and the fixture broker are not startup dependencies;
a worker with no active subscriptions remains running. Compose invokes the existing
Python entrypoint directly; deployment health probes and operator packaging are
deferred to M2. The profiles are separate so
using the worker never provisions a customer broker. Compose's worker grace is
60 seconds; keep it longer than any overridden drain deadline.

To stop the example, first pause/retire its subscription through normal controls,
then stop the worker with its grace period and remove only the disposable broker:

```bash
uv run --project backend podman-compose --profile kafka-worker stop kafka-worker
uv run --project backend podman-compose --profile kafka stop kafka
uv run --project backend podman-compose --profile kafka rm -f kafka
```

Removing this broker destroys its source history. Do not reuse existing
subscriptions against a newly created fixture broker as if it were the old source.
Do not run broad volume-removal commands against a stack containing evidence you
need. See [worker operations](../../docs/kafka-worker-operations.md) for recovery
ordering and retention safeguards. Live startup, TLS compatibility and workflow
execution of this fixture remain later verification work.
