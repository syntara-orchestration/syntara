# EP facade read-query contract

The AO facade forwards these list requests to the independent EP service:

| AO path | EP path |
|---|---|
| `/api/execution_plane/v1/work_items` | `/v1/work-items` |
| `/api/execution_plane/v1/execution_targets` | `/v1/execution-targets` |

Both accept `limit` (default 20, maximum 100), `cursor`, `sort`, and `include_total`.
An omitted sort stays omitted: EP defaults work items to newest first and targets
to oldest first. Cursors are opaque; AO forwards them without decoding or rebuilding
next/prev tokens. Keep the same filters, sort, and page size during navigation.

Filtering uses Syntara/EP bracket syntax, including `id[in]=<uuid1>,<uuid2>`,
`name[contains]=worker`, `enabled=false`, `created_at[gte]=2025-06-01`, and
`claimed_at[isnull]=true`. Targets also support `labels[env]=prod` and label-key
existence checks such as `labels[env]=`. Empty filter values and commas survive
forwarding. EP owns the field/operator allowlists and typed value validation;
unknown filters reach EP and its HTTP 422 response is returned to the AO caller.

AO validates the page envelope and its curated resource models. It preserves
`next`, `prev`, and `total` from EP, including filtered totals, rather than deriving
navigation or counting resources locally. Invalid JSON/envelopes/resources and
internal service authentication/endpoint failures produce HTTP 502; connectivity
failures, rate limits, and EP server errors produce HTTP 503.

Example requests (substitute UUIDs and URL-encode query values):

```text
GET /api/execution_plane/v1/work_items?id[in]=<uuid1>,<uuid2>&include_total=true
GET /api/execution_plane/v1/work_items?status[in]=pending,failed&claimed_at[isnull]=true
GET /api/execution_plane/v1/execution_targets?labels[env]=prod&enabled=true&sort=name&limit=2
GET /api/execution_plane/v1/execution_targets?labels[env]=prod&enabled=true&sort=name&limit=2&cursor=<next-or-prev-token>
```

This patch changes query transport and response handling. Existing authorization
checks are preserved; project associations and RBAC are a separate next step.
EP also has a cluster list, but this AO router currently exposes only
work items and execution targets. No cluster list route is introduced here.
