# Service-to-Service Certificate Authentication

Internal services authenticate via mTLS client certificates. The certificate's Common Name (CN) identifies the calling service and gates access to service-level privileges (OPA bypass, audit identity, `X-On-Behalf-Of` trust).

## Architecture

Three layers handle cert-based authentication:

### 1. TLS Protocol — Certificate Extraction

Uvicorn does not natively expose client certificates in the ASGI scope. A custom HTTP protocol subclass (`syntara.core.tls.protocol.TLSAutoProtocol`) overrides `connection_made()` to extract the peer certificate from the asyncio transport's `ssl_object` and injects it into the ASGI scope at `scope["extensions"]["tls"]["peercert"]`.

`TLSAutoProtocol` auto-selects between httptools and h11 backends, matching uvicorn's own detection. The injection point differs per backend — `on_headers_complete()` for httptools, `handle_events()` for h11 — but the result is the same: the parsed peercert dict is available before any ASGI middleware runs.

### 2. Certificate Middleware — CN Validation

`ClientCertAuthMiddleware` (`syntara.auth.cert_middleware`) is registered as the outermost ASGI middleware. It reads the peercert from the scope extension and performs validation in order:

1. **CN extraction** — missing CN → 403
2. **CRL revocation check** — revoked serial → 403
3. **CN allowlist check** — determines whether the CN receives service identity. CNs not on the allowlist proceed without service identity (request continues, falls through to JWT auth). Only revocation and missing CN produce hard 403s.

On success, the middleware sets two values in `scope["state"]`:

| Key | Value |
|-----|-------|
| `is_cert_authenticated` | `True` if CN is on the allowlist |
| `cert_cn` | The CN string (e.g. `backend.ao.svc`), or `None` if not on allowlist |

For non-service-identity requests (no cert, or CN not on allowlist), the middleware strips the `X-On-Behalf-Of` header to prevent spoofing.

The middleware is a no-op when `APP_S2S_TLS_ENABLED=false` and skips paths in `EXCLUDED_PATHS` and `EXCLUDED_PATH_PREFIXES` (defined in `syntara.api.constants`).

### 3. Auth Dependencies — User Resolution

`get_current_user()` (`syntara.auth.dependencies`) checks for a JWT Bearer token first. If absent, it falls back to cert authentication by reading `request.state.is_cert_authenticated`.

For cert-authenticated requests, `_user_from_cert()` builds a synthetic `User`:

- If an `X-On-Behalf-Of` header is present (trusted because the middleware only preserves it for cert-authenticated requests), the header's UUID becomes the user's `id` — preserving `created_by` attribution to the originating human.
- Otherwise, a deterministic UUID is derived from the CN via `service_principal_id()` (UUID5 with a fixed namespace).

## Certificate Identity Model

Each service has a distinct CN matching the production naming convention:

| Service | CN | Receives Service Identity |
|---------|----|----|
| Backend | `backend.ao.svc` | Yes |
| Worker | `worker.ao.svc` | Yes |
| Background Worker | `background-worker.ao.svc` | Yes |
| Temporal | `temporal.ao.svc` | Yes |
| UI (nginx) | `ui.ao.svc` | **No** |

The UI CN is deliberately excluded from the allowlist. The UI's nginx proxy presents a client cert for transport trust (proving it's the real UI pod), but user requests through nginx must fall through to JWT auth. Without this exclusion, the UI cert would grant service identity — bypassing OPA authorization and logging all user requests as a service actor.

The canonical list of service CNs is defined in `syntara.core.models.principal.KNOWN_SERVICE_CNS` and validated against the cert generation tool at import time.

## Certificate Requirements

Each service needs a certificate signed by a shared CA with:

- A **distinct CN** per service (e.g. `backend.ao.svc`, `worker.ao.svc`) — the middleware uses the CN as the service's identity
- **Extended Key Usages**: both `serverAuth` and `clientAuth` — each service certificate is used for serving HTTPS and for client authentication when calling other services
- **Subject Alternative Names**: include the DNS names the service is reachable at (e.g. compose service names, Kubernetes Service FQDNs, `localhost`)

All services must trust the same CA. Set `APP_S2S_TLS_CA_CERT_PATH` to the CA certificate, and `APP_S2S_TLS_CERT_PATH` / `APP_S2S_TLS_KEY_PATH` to the service's own cert and key. Set `APP_S2S_TLS_CN_ALLOWLIST` to the JSON list of CNs that should receive service identity — typically the backend, worker, background-worker, and temporal CNs (not the UI).

When `APP_S2S_TLS_ENABLED=true`, `main.py` automatically configures uvicorn with HTTPS serving, the custom TLS protocol for cert extraction, and TLS 1.3 minimum. No additional uvicorn configuration is needed beyond the environment variables.

For local development, `tools/generate_certs.py` generates a CA and per-service certificates with the correct CNs and EKUs.

## Configuration Reference

| Environment Variable | Default | Description |
|-----|---------|-------------|
| `APP_S2S_TLS_ENABLED` | `false` | Enable mTLS for all internal S2S communication. Recommended for production |
| `APP_S2S_TLS_CA_CERT_PATH` | — | CA certificate for verifying peer certificates |
| `APP_S2S_TLS_CERT_PATH` | — | This service's certificate (serving, client auth, Temporal) |
| `APP_S2S_TLS_KEY_PATH` | — | This service's private key |
| `APP_S2S_TLS_CN_ALLOWLIST` | `null` | JSON list of CNs granted service identity. When `null`, no CN receives service identity |
| `APP_S2S_TLS_CRL_PATH` | — | PEM-encoded CRL. Certificates with revoked serials get hard 403 |

All paths are required when `APP_S2S_TLS_ENABLED=true`. The CRL path is optional.

## Request Flow

```
Client connects with TLS client cert
  → TLSAutoProtocol.connection_made() extracts peercert from ssl_object
  → TLSAutoProtocol injects peercert into scope["extensions"]["tls"]
  → ClientCertAuthMiddleware reads peercert from scope
  → Validates CN exists, checks CRL, checks CN allowlist
  → Sets scope["state"]["is_cert_authenticated"] and scope["state"]["cert_cn"]
  → Strips X-On-Behalf-Of if not cert-authenticated
  → get_current_user() sees is_cert_authenticated=True
  → Builds service User from CN (or X-On-Behalf-Of UUID)
  → Request proceeds with service identity (OPA bypass, audit as service actor)
```

For UI/proxy requests (CN not on allowlist):

```
UI nginx connects with ui.ao.svc cert
  → Middleware sees CN not in allowlist
  → is_cert_authenticated=False, cert_cn=None
  → X-On-Behalf-Of stripped
  → get_current_user() falls through to JWT auth
  → Request authenticated as the human user from JWT
```

## TLS Client Certificate Requirement

`main.py` defaults to `ssl.CERT_OPTIONAL` — client certs are validated when present but not required. This allows the backend to serve clients that don't present certs (e.g. health probes, frontend dev servers).

Production deployments can override this to `CERT_REQUIRED` (e.g. via `--ssl-cert-reqs 2`) when all clients are cert-aware. Under `CERT_REQUIRED`, any reverse proxy (e.g. nginx) fronting the backend must also present a valid client cert — this is why the UI gets its own certificate (`ui.ao.svc`), even though it doesn't receive service identity.

## Local Development

The `make setup` target generates dev certificates via `tools/generate_certs.py`.
Re-running `make certs-generate` (or any target that depends on `_ensure-certs`) backfills
missing per-service files under the existing CA — use `make certs-generate-force` only when
you need to rotate the whole set.

Set `APP_S2S_TLS_CN_ALLOWLIST` in `podman-compose.yml` to test allowlist behavior locally:

```
APP_S2S_TLS_CN_ALLOWLIST=["backend.ao.svc","worker.ao.svc","background-worker.ao.svc","temporal.ao.svc"]
```
