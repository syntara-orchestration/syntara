# The `/_internal/` Path Prefix — Security Model

Paths under `/_internal/` are **not** an authentication mechanism. They are an
**exclusion list**: the prefix removes cross-cutting middleware from a request.
Adding an endpoint there strips protections rather than adding them.

Read this before putting anything new under `/_internal/`.

## What the prefix actually does

`EXCLUDED_PATH_PREFIXES` in `src/syntara/api/constants.py` is `("/_internal/", "/api_docs/")`.
Four middlewares return early for any path matching it:

| Middleware | Location | Consequence for `/_internal/` |
|---|---|---|
| `ClientCertAuthMiddleware` | `src/syntara/auth/cert_middleware.py` | No mTLS validation; `request.state.is_cert_authenticated` is never set; **`X-On-Behalf-Of` is never stripped** |
| `AuditMiddleware` | `src/syntara/audit/middleware.py` | No HTTP-level audit record (source IP, latency, headers, read access) |
| `MetricsMiddleware` | `src/syntara/metrics/middleware.py` | No request metrics |
| `RateLimitMiddleware` | `src/syntara/rate_limiting/middleware.py` | **No rate limiting** |

The `X-On-Behalf-Of` consequence is the sharpest one. For normal paths the cert
middleware *strips* that header from any request that is not cert-authenticated
(`cert_middleware.py`, `_strip_header`), which is the only reason
`get_current_user` is allowed to trust it (`auth/dependencies.py`,
`_user_from_cert`). Under `/_internal/` the strip never runs, so a handler that
reads the header directly is trusting a caller-supplied identity.

## The assumption, stated plainly

The security model for `/_internal/` is **network isolation** — that these paths
are unreachable from outside the cluster.

**That assumption is currently unenforced and unverified in this repository.**
There is no NetworkPolicy, ingress rule, or listener separation here that
implements it, and no test asserts it. `/_internal/` is served by the same
application on the same port as the public API. Treat "internal" as a naming
convention, not a control, unless and until the deployment enforces it.

## Consequences for endpoint design

An endpoint under `/_internal/` must satisfy **both**:

1. It carries its own access control, and
2. Exposure to an unauthenticated caller is acceptable.

The existing internal metrics endpoints (`api/main.py`, `_INTERNAL_METRICS_PREFIX`)
meet this: every handler calls `_guard()` in `metrics/internal_api.py`, which
returns 404 unless the runtime setting `metrics.perf_test_mode` is enabled —
**default `False`** (`settings/catalog.py`). They are switched off in production
rather than merely hidden.

Do **not** assume "other `/_internal/` endpoints have no auth, so mine needs
none." They have a kill switch. An endpoint that mutates state, spends money
(LLM calls), or reads tenant data does not belong here without an equivalent
gate — and, given the rate-limit exclusion, an unauthenticated state-mutating
endpoint here is a resource-exhaustion vector.

## Why the invocations API is not under `/_internal/`

The invocations API is internal plumbing — six endpoints used by the Temporal
worker — and was a candidate for this prefix (AAP-86106, PR #47). It stayed at
`/api/v1/invocations` with `include_in_schema=False` (PR #257) because moving it
would have:

- broken authentication — the worker authenticates by mTLS + `X-On-Behalf-Of`,
  and the prefix disables both the cert check and the anti-spoof strip, so the
  endpoint would have accepted an arbitrary caller-supplied user id;
- dropped the admin-only RBAC (`PermissionChecker("invocation", …)`) with no
  replacement;
- dropped audit and rate limiting;
- removed the `callback_url` sanitisation that keeps non-cert callers from
  supplying their own callback target (SSRF).

Hiding it from the public OpenAPI contract achieved the actual goal — it is not
a customer-facing API — while keeping every protection. See
`docs/standards/openapi-spec-management.md` for how internal paths are kept out
of the public spec.

## Audit posture

`/_internal/` requests produce **no HTTP-level audit record**: no source IP, no
latency, no headers, and no record of reads. This is a deliberate consequence of
the exclusion list, not an oversight.

Application-level audit still fires where the domain emits it — invocation
creation dispatches `InvocationCreatedEvent` from `InvocationService`, and
database triggers cover row changes — so *what* changed is recorded even though
*who called over HTTP, from where* is not.

If an internal endpoint needs HTTP-level audit, it cannot live under this prefix
as things stand; either give it a normal path or narrow `EXCLUDED_PATH_PREFIXES`
so the audit middleware still runs for it.

## Related

- `src/syntara/api/constants.py` — the exclusion list itself
- `docs/s2s-cert-authentication.md` — how internal services actually authenticate
- `docs/audit.md` — audit architecture
- `docs/standards/openapi-spec-management.md` — keeping internal paths out of the public spec
