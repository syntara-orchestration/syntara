# Execution Plane: Workload data sharing

How successive WorkItems in one Automation Orchestrator (AO) workflow
share a workspace, and how a run pushes file results. Object-store
files and Git trees are not Execution Plane input schemes: AO fetches
them with a dedicated activity (HTTP or Git) into the workspace.

- Ticket: [AAP-94189](https://redhat.atlassian.net/browse/AAP-94189)
- Feature: [ANSTRAT-1803](https://redhat.atlassian.net/browse/ANSTRAT-1803)
- Parent epic: [AAP-82060](https://redhat.atlassian.net/browse/AAP-82060)
- Labels contract: [syntara#620](https://github.com/syntara-orchestration/syntara/pull/620)
- Placement examples: [syntara#634](https://github.com/syntara-orchestration/syntara/pull/634)

## What this document is

A first cut of the **data-sharing contract** on the WorkItem payload.
It names the use-cases, who owns each side, and a payload shape EP can
implement without knowing what a Project or Workflow is.

It is not a Kubernetes PVC spec and not a Podman volume spec. Those
are the same concept on different backends. It is not AO FileManager
internals ([file-storage.md](../file-storage.md)), and not the
in-container SDK. Listed outputs are paths. HTTP(S) files and Git
trees are dedicated activities writing into the workspace. The
workspace is a volume with a globally unique UUID, on one
ExecutionTarget.

Placement stays in [labels.md](labels.md). The reconciler does not
read this payload. See [example 02](examples/02-volume-mount.md)
for a cold-start inventory that ignores data sharing when matching.

## Principles

1. **Outputs and workspace are not placement.** They do not select an
   ExecutionTarget. There is no `volume-mount` selector. A workspace
   **id** is unique across every ExecutionTarget and the volume lives
   on exactly one of them, so WorkItems that cite that id run on that
   target. AO already owns that (selectors or default routing). The
   reconciler still does not read `data`.
2. **HTTP and Git are activities, not `data.inputs`.** Fetching
   object-store bytes is a WorkItem whose `activity.image` is an HTTP
   client (for example `registry.redhat.io/ao/http-request:1.0.0`).
   Fetching a Git tree is a WorkItem whose image is a Git client (for
   example `registry.redhat.io/ao/git-clone:1.0.0`). Both write into
   `/workspace`. The workspace *is* a volume (Kubernetes PVC or
   Podman volume; same concept). There is no `data.inputs` list.
3. **AO resolves Git refs and HTTP URLs before submit.** EP does not
   call `POST /files`, look up `FileMetadata`, or resolve a Git
   branch name. AO turns a file id into an HTTP(S) URL on the HTTP
   activity, and a repo ref into a clone URL plus SHA on the Git
   activity.
4. **JSON result ≠ file artifacts.** `WorkItem.result` stays a small
   JSON blob (stdout, return code, artifact URIs). Large files go to
   object storage. Temporal payload limits make that split mandatory.
5. **A workspace has a UUID unique across all ExecutionTargets.** The
   volume lives on exactly one target. It is mounted at `/workspace`
   by default. ReadWriteOnce: **only one WorkItem can mount that
   workspace at a time.** Purge is a TTL (for example 3 hours from
   last unmount) or an API call; EP deletes the volume. Volume size
   is the ExecutionTarget default; there is no per-workspace override
   for now.

## Primary use-cases

| # | Use-case | What the WorkItem carries | When it happens |
|---|---|---|---|
| 1 | **Share a workspace** | Globally unique workspace **UUID**. Volume on one ET at `/workspace`. **One WorkItem at a time.** | Until TTL from last unmount, or delete API |
| 2 | **Push results** | List of in-container file paths to upload | After the run, **in the background**; does not gate the next WorkItem. Artifacts land on `WorkItem.result` with `status` `uploading`, then `available` or `failed` |

Object-store files and Git trees are not payload use-cases. AO runs
an HTTP or Git activity against a URL or clone it already resolved
and writes under `/workspace`. Later nodes mount the same workspace
UUID.

Both use-cases use the same payload block. They compose: a node can
read and write `/workspace` and list files to upload as results.

## Fetching files into the workspace (not payload use-cases)

The author attached files, pointed at a bucket, or pointed at a Git
repo. Those bytes belong on the **workspace**, not on `data.inputs`.
There is no `data.inputs` list. AO submits a dedicated activity that
writes under `/workspace`.

### HTTP (object store)

AO already stores uploads in S3-compatible storage
([file-storage.md](../file-storage.md)). It turns a file id into an
HTTP(S) URL (presigned, or the platform file HTTP API) and submits a
WorkItem whose activity is HTTP:

```json
{
  "payload": {
    "activity": {
      "image": "registry.redhat.io/ao/http-request:1.0.0",
      "params": {
        "url": "https://files.example.com/files/abc123/site.yml",
        "dest": "/workspace/site.yml"
      }
    },
    "data": {
      "workspace": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7"
    }
  }
}
```

`activity.params` is owned by the HTTP activity (AO / Extension), not
by this contract. The activity must write the body to a filesystem
path (for example `dest`), not only into `WorkItem.result`.

Same pattern for a minted artifact URI from use-case 2: a later HTTP
activity GETs that URL into `/workspace`. A different target cannot
mount that UUID; AO runs the HTTP activity there into a workspace on
that target, or the next node consumes the URI itself.

### Git

AO turns the author's branch or tag into a clone URL plus a **pinned
commit SHA** (the same way it resolves an image tag → digest for
`activity.image`) and submits a Git activity:

```json
{
  "payload": {
    "activity": {
      "image": "registry.redhat.io/ao/git-clone:1.0.0",
      "params": {
        "uri": "git+https://gitlab.example.com/org/playbooks.git",
        "ref": "a1b2c3d4e5f6",
        "dest": "/workspace/src"
      }
    },
    "data": {
      "workspace": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7"
    }
  }
}
```

`activity.params` is owned by the Git activity, not by this contract.
EP does not follow `main`. A floating branch name would make two
nodes of one execution clone different trees. Credentials are a
Credential Provider reference on the activity, not a password in the
URI.

The clone is writeable on disk like any other workspace files. Pushing
commits back to the remote is not a use-case here; later nodes see
whatever was left under `/workspace`.

Submodules, LFS, sparse checkout, and clone depth are the Git
activity's problem, not EP's. Lean MVP for that Extension: one repo,
one SHA, full tree, shallow clone, no LFS.

### What EP does

That WorkItem mounts the workspace UUID; the activity writes at a
path under `/workspace`. The next WorkItem on the same UUID reads
the files. There is no Worker Manager GET or `git clone` at start of
the playbook (or other) WorkItem.

OpenShell has no volume attach. HTTP and Git activities still run;
they cannot leave files on a workspace for the next WorkItem.
Cross-run files on that backend go through use-case 2 (listed
outputs) or stay in that one container.

[Example 02](examples/02-volume-mount.md) used
`payload.volume_mounts` as a stand-in. Read that as the workspace
volume, not as an input list.

## Use-case 1: share a workspace across WorkItems

A **workspace** is a volume (Kubernetes PVC or Podman volume; same
concept) identified by a **UUID that is unique across all
ExecutionTargets**. That volume lives on **exactly one**
ExecutionTarget. There is no second workspace with that UUID, on this
target or any other.

WorkItems that carry that id run on the target that holds the volume
and see it at `/workspace` by default. Node A writes a file; node B
with the same id reads it. No S3 round-trip.

```text
workspace id 7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7  →  unique in the Execution Plane
                          →  volume on ExecutionTarget ep-default
                          →  mounted at /workspace

AO execution
  node A  WorkItem  workspace=7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7  →  ep-default  →  writes /workspace/state.json
  node B  WorkItem  workspace=7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7  →  ep-default  →  reads  /workspace/state.json
```

AO mints the UUID and creates the volume through an API call against
the Execution Plane. EP creates the volume on the chosen
ExecutionTarget, using that target's **default workspace size**, and
refuses the UUID if it already exists anywhere. There is no size
field on the WorkItem and no per-workspace override for now.

The WorkItem carries the **UUID**, not a PVC or Podman volume id. The
Worker Manager looks up which target holds that UUID and mounts it.

```json
"data": {
  "workspace": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7"
}
```

| Field | Meaning |
|---|---|
| `data.workspace` | Workspace **UUID**. Unique across every ExecutionTarget. |
| Mount path | `/workspace` by default. Override with `{ "id": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7", "path": "/work" }`. |
| Size | Default on the **ExecutionTarget**. The WorkItem and the workspace create API do not override it. |

Omitted `workspace` means this WorkItem does not mount a workspace.

The volume is ReadWriteOnce. Kubernetes and Podman both refuse a
second RW mount of the **same** volume. **Only one WorkItem can use
that workspace at a time.** The Work Scheduler does not dispatch a
second item for that id until the first has exited and released the
mount. Parallel nodes that share an id must be sequenced by AO (or
they queue). Parallel work that must not wait uses a different
workspace id, a different target, or use-case 2.

Sharing requires **placement on the target that owns the id**. AO
keeps those WorkItems together with selectors, or they all take
[default routing](executiontarget-reconciler.md#default-routing)
to the same protected default. The reconciler does not read the
workspace id. A WorkItem whose workspace lives on `ep-default` but
whose selectors land it elsewhere cannot see that volume; pass files
through use-case 2 instead.

### Volume life time

AO owns workspace lifetime. **Creation** is an API call against the
Execution Plane: AO mints the UUID, then creates the volume (`POST`
id, target, optional TTL). EP creates the volume on that
ExecutionTarget and refuses the UUID if it already exists anywhere.

**Deletion** is EP deleting the volume. Two ways:

| How | Who | When |
|---|---|---|
| **TTL** | Execution Plane | For example `3h` **after last unmount**. EP deletes the workspace when that timer fires. |
| **API** | AO | `DELETE` the workspace by id against the Execution Plane, at any time (for example when the AO execution finishes). |

TTL is set when the workspace is created. The clock is **last
unmount**: it starts when a WorkItem that held the volume exits,
and it resets on every later unmount of the same id. A workspace
that is still mounted is never deleted; a long run can outlive the
original TTL. If the volume was never mounted, create time counts
as the last unmount (idle from birth).

Git and object-store files are **not** a second volume. They arrive
because an HTTP or Git activity wrote under `/workspace`. Mutable
state later nodes must see uses the same directory.

OpenShell has no volume attach. Workspaces on OpenShell are an open
question (SDK snapshot, or no shared directory).

## Use-case 2: collect results after each execution

Two kinds of "result":

| Kind | Where it lives | Size |
|---|---|---|
| **Status JSON** | `WorkItem.result`, then the Completion Notifier / Temporal callback | Small. Today's `ScriptOutput` (return code, stdout, stderr) plus artifact URIs. |
| **File artifacts** | Object storage | Large. |

The WorkItem names **which files** to upload. That is enough. It does
not name a destination URI. After the container exits, the Worker
Manager / SDK harvests the listed paths, mints an object key for
each, and the WorkItem can complete. **Upload to object storage (S3)
runs in the background.** It does not delay AO triggering the next
WorkItem. Each artifact on `WorkItem.result` has a `status`
(`uploading` until that PUT finishes, then `available` or `failed`)
and a `size` in bytes (from harvest). AO uses `available` URIs to
show or chain artifacts that are not still on a shared workspace.

```json
"data": {
  "outputs": [
    "/work/out/report.json",
    "/work/out/summary.txt"
  ]
}
```

```json
"result": {
  "output": { "...": "status JSON" },
  "artifacts": [
    {
      "path": "/work/out/report.json",
      "uri": "s3://orchestrator-files/artifacts/wi-7c1a/report.json",
      "status": "available",
      "size": 12480
    },
    {
      "path": "/work/out/summary.txt",
      "uri": "s3://orchestrator-files/artifacts/wi-7c1a/summary.txt",
      "status": "uploading",
      "size": 882
    }
  ]
}
```

Both objects are on the result as soon as the WorkItem completes.
`uri` is the minted key (stable from harvest). `size` is the file
size in bytes at harvest. `status` starts as `uploading`, then
`available` when that PUT succeeds, or `failed` when it errors.
PUTs can finish at different times; the snapshot above is mid-flight.

| Field | On the WorkItem | Meaning |
|---|---|---|
| `data.outputs[]` | payload, at submit | In-container file path to upload. No `uri`. |
| `result.artifacts[].path` | result, from complete | Same path, so AO can match. |
| `result.artifacts[].uri` | result, from complete | Object key minted at harvest. GET-able only when `status` is `available`. |
| `result.artifacts[].status` | result, from complete | `uploading`, `available`, or `failed`. |
| `result.artifacts[].size` | result, from complete | File size in bytes, taken at harvest. |

AO does not pick object keys before submit. A later node that needs
an artifact right away already shares the workspace (the file is
still on disk; no wait on S3). A node that consumes the minted URI
waits until that artifact is `available`, then runs an HTTP activity
that GETs it into `/workspace`. `failed` means the PUT errored; AO
must not wait on `uploading` forever. There is no `data.inputs` list.

Push happens even on failure when a listed file exists: partial
artifacts are often what the author needs. Whether a failed run still
uploads is an open question; leaning yes, with the JSON result still
`FAILED`. A listed path that the run never created is omitted from
`artifacts` (or recorded as missing — open question).

Status JSON does not go through S3. It stays on `WorkItem.result` as
today ([Work Store](work-store.md)). That JSON is what AO uses to
trigger the next WorkItem; it does not wait on the background PUT.

## Payload shape

Illustrative keys only. Not the final field design.

```json
{
  "selectors": {},
  "payload": {
    "activity": {
      "image": "registry.redhat.io/ao/ansible-playbook:1.0.0",
      "params": {
        "playbook": "site.yml"
      }
    },
    "data": {
      "outputs": [
        "/work/out/report.json",
        "/work/out/summary.txt"
      ],
      "workspace": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7"
    }
  }
}
```

| Block | Direction | Shared across WorkItems? |
|---|---|---|
| HTTP or Git activity + `workspace` | URL or clone → `/workspace` | Yes, once written. The fetch is its own WorkItem. |
| `outputs` | container → object store | No. List of files. URIs, `status` (`uploading` \| `available` \| `failed`), and `size` appear on `WorkItem.result`. |
| `workspace` | live directory, **UUID unique across all ExecutionTargets**, volume on one target | Yes, **successive** WorkItems on **that** UUID. One RW mount. Default path `/workspace`. Purged by TTL (from last unmount) or delete API. |

Omitted `outputs` / `workspace` mean "none". There is no
`data.inputs`.

`payload.volume_mounts` in [example 02](examples/02-volume-mount.md)
should be read as a sketch of the workspace volume, not of an input
list. This document replaces that sketch.

## Who does what

```
AO
  resolve file id → HTTP(S) URL; Git ref → clone URL + SHA
  place sharing nodes on one ExecutionTarget
    → HTTP or Git WorkItem (activity writes under /workspace)
    → later WorkItem.payload.data (workspace UUID, outputs)
        → Worker Manager
              workspace id → volume on its ExecutionTarget → /workspace
              outputs → harvest, mint keys (status=uploading); complete; S3 PUT in background (status=available or failed)
        → Work Watcher
              WorkItem.result (JSON + artifacts[].uri, status, size)
        → Completion Notifier → AO
```

| Concern | Owner |
|---|---|
| Upload UI, `POST /files`, `FileMetadata` | AO |
| Mint globally unique workspace UUID; create volume on one ET via EP API | AO |
| Default workspace size (no per-workspace override) | ExecutionTarget |
| Refuse duplicate workspace UUID | Execution Plane |
| Place WorkItems that share a workspace id on that target | AO (selectors or default routing) |
| Serialize dispatch per workspace id (one RW mount) | Work Scheduler |
| Delete workspace (`DELETE` by id against EP) | AO |
| Purge workspace (TTL from last unmount) | Execution Plane |
| Map file ids to HTTP(S) URLs; run HTTP activity into `/workspace` | AO |
| Map repo + branch/tag to clone URL + SHA; run Git activity into `/workspace` | AO |
| Credential reference for Git remote (or HTTP if not presigned) | AO → Credential Provider |
| Mount workspace id at `/workspace` | Worker Manager |
| Harvest listed output paths, mint keys (`status=uploading`); S3 PUT in the background (`status=available` or `failed`); does not gate the next WorkItem | Worker Manager / SDK |
| Write `artifacts[]` on `WorkItem.result`; patch `status` when a PUT finishes or fails | Work Watcher / Work Store |
| Match ExecutionTarget | ExecutionTarget Reconciler (ignores `data`) |

EP does not become a file manager. If the HTTP URL or Git remote is
unreachable from the ExecutionTarget, that fetch WorkItem fails. That
is a connectivity / credential problem, not a selector miss.

## Materialization (leaning)

The workspace is a volume on the ExecutionTarget. Object-store bytes
and Git trees arrive because an HTTP or Git activity wrote them
there. Listed outputs are uploaded to object storage in the
background after the run. That PUT does not delay the next WorkItem.

| Mechanism | Fits | Warm pool |
|---|---|---|
| **HTTP or Git activity** writing into `/workspace` | K8s and Podman (needs the workspace volume) | The activity itself yes; workspace is one holder per id |
| **Listed outputs** uploaded in the background after the run | All backends (K8s, Podman, OpenShell) | Yes. Does not gate the next WorkItem |
| **Workspace volume** (globally unique UUID, one ET) at `/workspace` | K8s PVC and Podman volume | One holder per id: concurrency 1 |

OpenShell has no volume attach. Listed outputs still work. Workspace
on OpenShell is an open question; HTTP and Git activities cannot leave
files for the next WorkItem via `/workspace` on that backend.

Leaning for MVP: **HTTP or Git activity + workspace** for inbound
files, **listed outputs** uploaded in the background after the run
(minting URIs into the result). That upload does not delay the next
WorkItem. The Worker Manager attaches the workspace UUID at
`/workspace`. It does not GET object storage or clone Git as WorkItem
inputs.

Because that volume is ReadWriteOnce, a second container cannot
mount the same id while the first WorkItem is running. Two different
ids are different volumes. That is not a per-WorkItem PVC create; it
is one id, one mount, one WorkItem.

Treat [example 02](examples/02-volume-mount.md) as the workspace
volume, not as an input list. Workspace is at `/workspace` unless
overridden.

## Sequence (workspace on one ExecutionTarget, two nodes)

```mermaid
sequenceDiagram
    participant AO as Automation Orchestrator
    participant WS as Work Store
    participant WM as Worker Manager
    participant C as container
    participant HTTP as HTTP activity
    participant Vol as workspace 7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7 on ep-default
    participant S3 as object storage

    AO->>WS: WorkItem A { image: http-request, workspace: 7c1a9f3e-… } on ep-default
    WM->>HTTP: start with /workspace mounted
    HTTP->>S3: GET url
    HTTP->>Vol: write /workspace/site.yml
    HTTP-->>WM: exit
    Note over Vol: RW volume released; only now can B mount the same id

    AO->>WS: WorkItem B { image: ansible-playbook, workspace: 7c1a9f3e-… } on ep-default
    WM->>C: start with same workspace id at /workspace
    C->>Vol: read /workspace/site.yml
    C->>Vol: write /workspace/state.json
    C-->>WM: exit
    WM->>WS: result JSON + artifacts status=uploading. Next WorkItem can start
    Note over Vol: RW volume released; S3 PUT does not hold the mount
    WM->>S3: PUT listed output files (background)
    WM->>WS: artifact status=available or failed
```

## Out of scope

| Omitted | Why |
|---|---|
| Placement / selectors | [labels.md](labels.md) |
| Live PVC / Podman volume or disk capacity as a selector | Not a label. Open question in labels.md. |
| AO file upload, conversion, RBAC | [file-storage.md](../file-storage.md) |
| In-container SDK API | Separate SDK design |
| Customer S3 IAM setup | Platform / credential work |
| Git write-back (commit, push, PR) | Git activity is clone into `/workspace`. Writes stay on the volume or go to `outputs`. |
| Cross-target workspace | An id exists on exactly one ExecutionTarget. Cross-target files: use-case 2, then an HTTP activity on the other target. |
| Per-workspace size override | Size is the ExecutionTarget default. Not on the WorkItem. |
| `data.inputs` | HTTP or Git activity + workspace instead. |
| Streaming stdout as files | Still `WorkItem.result` / log plumbing |

## Open questions

1. **SDK vs Worker Manager for listed outputs.** SDK-inside-the-image
   keeps backends honest and works on warm pools. Worker Manager copy
   after exit keeps images dumb. HTTP and Git fetch are activities,
   not this copy path.
2. **Credential reference shape.** Payload-level secret is wrong.
   HTTP and Git activities may take a Credential Provider id, or AO
   mints a presigned URL so an HTTP GET is unauthenticated.
3. **Failed runs and partial uploads.** Lean yes for listed
   `outputs`, so the author can inspect. Workspace files stay on the
   volume either way.
4. **Two workspace ids on one target at once.** Different volumes
   could in principle mount in parallel. Lean: serialize per id;
   two ids may run together if the target has capacity.
5. **OpenShell workspace.** No volume attach. Snapshot via SDK, or
   no shared directory on that backend. HTTP and Git activities then
   cannot leave files for the next WorkItem via `/workspace`.
6. **Minted object-key scheme.** Work item id + basename is enough
    for uniqueness. Exact prefix (`artifacts/wi-…/`) is an
    implementation choice, not a payload field.
7. **Listed path missing after the run.** Omit from `artifacts`, or
    record an error for that path. Lean: omit, do not fail the whole
    upload list.

Git extras (submodules, LFS, sparse checkout, clone depth) and Git
credentials (HTTPS token vs SSH key) belong to the Git activity
Extension, not this contract.

## Coordination

- **[example 02](examples/02-volume-mount.md):** cold-start inventory
  with a stand-in `volume_mounts` field. Read that field as the
  workspace volume. Matching still ignores it.
- **[labels.md](labels.md):** HTTP and Git activity params and
  workspace UUID are not labels. A workspace UUID is unique across
  all ExecutionTargets and the volume lives on one of them; AO uses
  selectors / default routing to keep WorkItems on that target.
- **[Worker Manager](worker-manager.md):** looks up the workspace id,
  mounts its volume at `/workspace` (one RW mount per id); harvests
  `data.outputs` and uploads them to object storage in the
  background. That PUT does not delay the next WorkItem. It does not
  GET object storage or clone Git as WorkItem inputs.
- **AAP-92722 (Work Scheduler):** do not dispatch a second WorkItem
  for a workspace id whose volume is still mounted.
- **Workspace API:** AO owns create (`POST` id, target, optional TTL)
  and `DELETE` by id against the Execution Plane. Size comes from
  the ExecutionTarget; create does not take a size. TTL (from last
  unmount) is an EP background task.
- **[Work Store](work-store.md):** `WorkItem.result` stays small JSON
  (run status plus `artifacts[]` with minted `uri`, `status`
  `uploading` | `available` | `failed`, and `size` in bytes). Artifact
  bytes are not a JSONB column. EP patches `artifacts[].status` when a
  background PUT finishes or fails.
- **[file-storage.md](../file-storage.md):** AO S3 for uploads. AO
  turns file ids into HTTP(S) URLs for the HTTP activity. EP does
  not import `FileManager`.
- **AAP-92720 (Work Executor):** persist `payload.data`; validate
  output paths and optional workspace id once a submission API
  exists.
- **HTTP activity (AO Extension):** writes the GET body under
  `/workspace`. Params such as `url` and `dest` are the Extension's.
- **Git activity (AO Extension):** clones a pinned SHA under
  `/workspace`. Params such as `uri`, `ref`, and `dest` are the
  Extension's.
- **Container SDK (AO / EP, separate design):** how the image reads
  `/workspace`, and how listed outputs are harvested for a background
  object-store upload.
