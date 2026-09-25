# Execution Plane: Workload data sharing

This document introduces two concepts:

1. **Workspace.** Successive WorkItems in one Automation Orchestrator
   (AO) workflow share a volume. That volume is the **workspace**: a
   UUID, on one ExecutionTarget, mounted at `/workspace` by default.
2. **Listed outputs.** Is a declarative list of files to retrieve.
   After a run, listed files are uploaded so later
   nodes or the UI can get them without stuffing bytes into
   `WorkItem.result`.

- Ticket: [AAP-94189](https://redhat.atlassian.net/browse/AAP-94189)
- Feature: [ANSTRAT-1803](https://redhat.atlassian.net/browse/ANSTRAT-1803)
- Parent epic: [AAP-82060](https://redhat.atlassian.net/browse/AAP-82060)
- Labels contract: [syntara#620](https://github.com/syntara-orchestration/syntara/pull/620)
- Placement examples: [syntara#634](https://github.com/syntara-orchestration/syntara/pull/634)

## What this document is

A first cut of the **data-sharing contract** on the WorkItem payload:
data sharing via the **workspace** feature. It names the use-cases,
who owns each side, and a payload shape EP can implement without
knowing what a Project or Workflow is.

The **workspace** is the same idea on every backend (Kubernetes PVC or
Podman volume). This is not a PVC spec, not AO FileManager
([file-storage.md](../file-storage.md)), and not the in-container SDK.
Listed outputs are filesystem paths.

Placement stays in [syntara#620](https://github.com/syntara-orchestration/syntara/pull/620).
The reconciler does not read this payload for the **first** WorkItem.
Reusing a volume workspace pins later WorkItems to the ExecutionTarget
that holds the volume
([example 02](examples/02-data-sharing-with-workspace.md)).

## Principles

1. **A new workspace is not a selector. Reusing one is placement.**
   There is no `volume-mount` label. The first WorkItem that cites a
   UUID is placed by selectors (or default routing). The reconciler
   does not read `data`. Once the volume exists on an ExecutionTarget,
   later WorkItems with that UUID run on **that** target. The Work
   Scheduler applies that pin. Listed `outputs` never place.
2. **Git and HTTP downloads are ordinary WorkItems.** There is no
   `data.inputs` list on the playbook (or other) WorkItem. To get a
   repo or a file onto disk, AO submits a WorkItem whose
   `activity.image` is a Git client (for example
   `registry.redhat.io/ao/git-clone:1.0.0`) or an HTTP client (for
   example `registry.redhat.io/ao/http-request:1.0.0`). That
   container writes into `/workspace`. EP does not clone or GET
   inside the Worker Manager.
3. **AO writes the exact link. EP just uses it.** The author may
   say "this file" or "branch main". AO turns that into something
   that cannot move **before** it submits the WorkItem: a download
   URL for a file it already stored
   ([file-storage.md](../file-storage.md)), or a clone URL plus one
   commit SHA for Git. EP does not ask AO "where is that file?" and
   does not ask Git "what is `main` today?"
4. **JSON result ≠ file bytes.** `WorkItem.result` stays a small
   JSON blob (stdout, return code). Large files go to object
   storage. The result may list **references** (`artifacts[]`: path,
   uri, status, size), not the bytes. Temporal payload limits make
   that split mandatory.
5. **A workspace has a UUID unique across all ExecutionTargets.** The
   volume lives on exactly one target. It is mounted at `/workspace`
   by default. ReadWriteOnce: **only one WorkItem can mount that
   workspace at a time.** Purge is a TTL (for example 3 hours from
   last unmount) or an API call; EP deletes the volume. Volume size
   is the ExecutionTarget default; there is no per-workspace override
   for now.

## Primary use-cases

| # | Use-case | What the WorkItem carries |
|---|---|---|
| 1 | **Share a workspace** | Globally unique workspace **UUID**. Volume on one ET at `/workspace`. **One WorkItem at a time.** |
| 2 | **Push results** | List of in-container file paths to upload |

To get a Git repo or an uploaded file onto disk, AO runs its Git or
HTTP WorkItem first, with the same workspace UUID. The playbook (or
other) WorkItem then reads `/workspace`. No extra EP fetch step.

Both numbered use-cases use the same payload block. They compose: a
node can read and write `/workspace` and list files to upload as
results.

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

AO mints the UUID and puts it on the WorkItem. It does not create the
volume: it does not know the ExecutionTarget yet. After the first
WorkItem is matched, and **before** it is dispatched, EP creates the
volume on that target, using the target's **default workspace size**,
and refuses the UUID if it already exists anywhere. There is no size
field on the WorkItem and no per-workspace override for now.

The WorkItem carries the **UUID**, not a PVC or Podman volume id. The
Worker Manager looks up which target holds that UUID and mounts it.
After the volume exists, later WorkItems with the same UUID are
dispatched to that ExecutionTarget.

```json
"data": {
  "workspace": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7"
}
```

| Field | Meaning |
|---|---|
| `data.workspace` | Workspace **UUID**. Unique across every ExecutionTarget. |
| Mount path | `/workspace` by default. Override with `{ "id": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7", "path": "/work" }`. |
| Size | Default on the **ExecutionTarget**. The WorkItem does not override it. |

Omitted `workspace` means this WorkItem does not mount a workspace.

The volume is ReadWriteOnce. Kubernetes and Podman both refuse a
second RW mount of the **same** volume. **Only one WorkItem can use
that workspace at a time.** The Work Scheduler does not dispatch a
second item for that id until the first has exited and released the
mount. Parallel nodes that share an id must be sequenced by AO (or
they queue). Parallel work that must not wait uses a different
workspace id, use-case 2, or an object-store snapshot with `ro` or
`copy`.

Once the volume exists, **reuse is a placement constraint.** The Work
Scheduler looks up the UUID, sees the volume on that ExecutionTarget,
and dispatches later WorkItems there. It does not ask the reconciler
again. Selectors on those later WorkItems do not pick a different
target.

### Alternative: object-store snapshot

A volume pins the workspace to **one** ExecutionTarget (one
cluster). The alternative is to publish a **full copy** of
`/workspace` to object storage (S3) when a writer exits, and
hydrate `/workspace` from that snapshot on the next WorkItem.

That snapshot is the **whole tree**, not use-case 2 listed files. Any
ExecutionTarget that can reach the bucket can run the next
WorkItem. AO does not have to keep those nodes on the same cluster.

```text
workspace id 7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7
                          →  snapshot s3://workspaces/7c1a9f3e-…/

AO execution
  node A  access=rw    →  cluster-1  →  writes /workspace  →  EP PUTs snapshot
  node B  access=ro    →  cluster-2  →  hydrates snapshot, reads only
  node C  access=copy  →  cluster-3  →  hydrates a private writable copy
```

B and C can run **in parallel** after A's snapshot is `available`.
They must not both be exclusive `rw` on the same generation.

Parallel use of one snapshot is only safe if AO flags each WorkItem:

| Flag | Disk | Parallel | Write-back |
|---|---|---|---|
| **`rw`** | Writable | **No.** One writer per generation (same idea as volume RWO). | Snapshot after exit becomes the next generation. |
| **`ro`** | Read-only | **Yes.** Many WorkItems, any cluster. | None. Nobody thinks they own the tree. |
| **`copy`** | Private writable copy | **Yes.** Many WorkItems, any cluster. | Local only unless AO publishes that copy as a new generation. Two parallel copies do not merge. |

Omitted flag is `rw`. Illustrative payload:

```json
"data": {
  "workspace": {
    "id": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7",
    "access": "ro"
  }
}
```

Unlike listed `outputs`, this PUT **can** gate the next WorkItem
when that item runs on another target: it cannot hydrate until the
snapshot is `available`. A successor on the **same volume** still
does not wait on S3.

| System | Pros | Cons |
|---|---|---|
| **Volume** (PVC / Podman volume) | Live directory; no pack/unpack. **Better for a large workspace:** the next WorkItem does not upload the tree. Next WorkItem on the same target is unmount + mount. Native Kubernetes and Podman. Writes are visible on disk immediately. | Pinned to one ExecutionTarget / cluster. ReadWriteOnce: one mount at a time; parallel nodes queue or split ids. Target going away takes the tree with it. OpenShell has no volume attach. |
| **Object-store snapshot** (S3) | Any cluster. Parallel `ro` or `copy` without RWO. Survives the original target. Hydrate into a container filesystem (OpenShell). | Full-tree PUT/GET every generation (time, bandwidth, cost). Cross-target next WorkItem waits for `available`. Parallel `copy` has no merge; two writers still need `rw` sequencing or an AO rule. Extra contract: snapshot format (tar vs prefix) and generation id. |

Leaning for MVP: **volume**. Snapshot is the path when AO must place
WorkItems on different clusters, run `ro` / `copy` in parallel, or
share a tree on a backend with no volume attach.

### Workspace life time

AO mints the UUID and later **deletes** it. **Creation** is not an AO
API call. EP creates the volume on the ExecutionTarget chosen for the
**first** WorkItem that cites that id, after reconcile and before
dispatch. AO does not pass a target. EP refuses the UUID if it already
exists anywhere.

**Deletion** is EP deleting the volume. Two ways:

| How | Who | When |
|---|---|---|
| **TTL** | Execution Plane | For example `3h` **after last unmount**. EP deletes the workspace when that timer fires. |
| **API** | AO | `DELETE` the workspace by id against the Execution Plane, at any time (for example when the AO execution finishes). |

TTL is the ExecutionTarget default, set when EP creates the volume.
The clock is **last unmount**: it starts when a WorkItem that held
the volume exits, and it resets on every later unmount of the same
id. A workspace that is still mounted is never deleted; a long run
can outlive the original TTL. If the volume was never mounted, create
time counts as the last unmount (idle from birth).


## Use-case 2: collect results after each execution (No Workspace)

Two kinds of "result":

| Kind | Where it lives | Size |
|---|---|---|
| **Status JSON** | `WorkItem.result`, then the Completion Notifier / Temporal callback | Small. Today's `ScriptOutput` (return code, stdout, stderr). |
| **File artifacts** | Object storage | Large. `artifacts[]` on the result is UI metadata (`path`, `uri`, `status`, `size`), not the bytes. |

The WorkItem names **which files** to upload. That is enough. It does
not name a destination URI.

After the container exits, the Worker Manager **copies listed paths
aside** (a spool), mints an object key for each, and **unmounts** the
workspace. The WorkItem can then complete. **Upload to object
storage (S3) runs in the background from that copy**, not from the
live volume. It does not delay AO triggering the next WorkItem. A
later WorkItem on the same UUID can mount immediately without tearing
the PUT.

Each artifact on `WorkItem.result` has a `status` (`uploading` until
that PUT finishes, then `available` or `failed`) and a `size` in
bytes (from harvest). That metadata is for the UI. **Chaining does
not wait on it.** Temporal already completed.

How a later node gets the bytes:

| Situation | How |
|---|---|
| **Same namespace** | GET an HTTP server on the **producer** WorkItem's sidecar. That sidecar outlives the activity container and exposes the harvested spool. Only reachable in that namespace. It can serve before the S3 PUT is `available`. |
| **Other cluster / other namespace** | The consumer activity calls a **localhost HTTP API** on **its** sidecar. That sidecar holds object-store credentials and GETs S3. It retries until `available` or `failed`. |

A CLI is a wrapper around those HTTP APIs, not a second protocol.
The activity image does not get S3 credentials.

The sidecar is the observer the Completion Notifier cannot be: the
next WorkItem is already running; the fetch blocks **inside the
container at first use**. Same-namespace traffic hits the producer
sidecar; cross-namespace traffic hits S3 through the consumer
sidecar. Do not add a dedicated HTTP-activity WorkItem per artifact
for this. HTTP and Git activities stay the path for AO-resolved
**inputs** (file id → URL, Git SHA).

```json
"data": {
  "outputs": [
    "/workspace/out/report.json",
    "/workspace/out/summary.txt"
  ]
}
```

```json
"result": {
  "output": { "...": "status JSON" },
  "artifacts": [
    {
      "path": "/workspace/out/report.json",
      "uri": "s3://orchestrator-files/artifacts/wi-7c1a/report.json",
      "status": "available",
      "size": 12480
    },
    {
      "path": "/workspace/out/summary.txt",
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
The sidecar uses `path` (and the producer WorkItem id), not AO polling
`status`. Same-namespace GETs can hit the producer sidecar's spool
directly.

| Field | On the WorkItem | Meaning |
|---|---|---|
| `data.outputs[]` | payload, at submit | In-container file path to upload. No `uri`. |
| `result.artifacts[].path` | result, from complete | Same path, so AO and the sidecar can match. |
| `result.artifacts[].uri` | result, from complete | Object key minted at harvest. Sidecar GET-able only when `status` is `available`. UI may show it. |
| `result.artifacts[].status` | result, from complete | `uploading`, `available`, or `failed`. UI. Sidecar waits; AO does not. |
| `result.artifacts[].size` | result, from complete | File size in bytes, taken at harvest. |

AO does not pick object keys before submit. There is no `data.inputs`
list. `failed` means the PUT errored; the sidecar must not wait on
`uploading` forever.

Push happens even on failure when a listed file exists: partial
artifacts are often what the author needs. Whether a failed run still
uploads is an open question; leaning yes, with the JSON result still
`FAILED`. A listed path that the run never created is omitted from
`artifacts` (or recorded as missing — open question).

Status JSON does not go through S3. It stays on `WorkItem.result` as
today ([Work Store](work-store.md)). That JSON is what AO uses to
trigger the next WorkItem; it does not wait on the background PUT.

## Getting Git and HTTP files onto `/workspace`

The author attached a file, pointed at a bucket, or pointed at a Git
repo. EP does not grow a fetch feature for that. AO submits a normal
WorkItem whose image already speaks HTTP or Git. That WorkItem
writes under `/workspace`. The next WorkItem on the same UUID sees
the files. There is no `data.inputs` list.

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

Same pattern is **not** used for use-case 2 listed outputs. A later
node that does not share the workspace pulls through the Worker
Manager sidecar (localhost HTTP), not through a second HTTP-activity
WorkItem. A different target cannot mount that UUID; AO either
shares a workspace on that target, uses an object-store snapshot, or
the next node calls the sidecar.

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

That WorkItem mounts the workspace UUID; the Git or HTTP image writes
at a path under `/workspace`. The next WorkItem on the same UUID
reads the files. The Worker Manager does not clone or GET as a
start-of-run step on the playbook WorkItem.

OpenShell has no volume attach. HTTP and Git activities still run;
they cannot leave files on a workspace for the next WorkItem.
Cross-run files on that backend go through use-case 2 (listed
outputs) or stay in that one container.

[Example 02](examples/02-data-sharing-with-workspace.md) is three WorkItems on one
volume workspace. Files under `/workspace` are still there for the
next WorkItem. There is no `data.inputs` list.

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
        "/workspace/out/report.json",
        "/workspace/out/summary.txt"
      ],
      "workspace": "7c1a9f3e-4b2d-41a8-9c1f-91c0d4e5a6b7"
    }
  }
}
```

| Block | Direction | Shared across WorkItems? |
|---|---|---|
| HTTP or Git WorkItem + `workspace` | URL or clone → `/workspace` | Yes, once that Git/HTTP WorkItem has written. |
| `outputs` | container → object store | No. List of files. Copy-aside, then background PUT. UI metadata on `WorkItem.result`. Cross-volume consume via sidecar. |
| `workspace` | live directory, **UUID unique across all ExecutionTargets**, volume on one target | Yes, **successive** WorkItems on **that** UUID. Reuse pins those WorkItems to that target. One RW mount. Default path `/workspace`. Purged by TTL (from last unmount) or delete API. |

Omitted `outputs` / `workspace` mean "none". There is no
`data.inputs`.

[Example 02](examples/02-data-sharing-with-workspace.md) is the volume workspace
payload (`data.workspace`), not an input list.

## Who does what

```
AO
  resolve file id → HTTP(S) URL; Git ref → clone URL + SHA
    → HTTP or Git WorkItem (workspace UUID)
        → Work Scheduler
              first UUID: reconcile, create volume on selected ET
              reuse: pin to the ET that holds the volume
        → Worker Manager
              workspace id → volume on its ExecutionTarget → /workspace
              outputs → copy aside, mint keys, complete, unmount; S3 PUT from copy (background)
              sidecar on later WorkItems → GET artifact (retry until available or failed)
        → Work Watcher
              WorkItem.result (JSON + artifacts[].uri, status, size)
        → Completion Notifier → AO
```

| Concern | Owner |
|---|---|
| Upload UI, `POST /files`, `FileMetadata` | AO |
| Mint globally unique workspace UUID | AO |
| Create volume on the selected ET (first WorkItem, after reconcile, before dispatch) | Work Scheduler |
| Default workspace size (no per-workspace override) | ExecutionTarget |
| Refuse duplicate workspace UUID | Execution Plane |
| Place the first WorkItem that cites a new workspace UUID | ExecutionTarget Reconciler (selectors; ignores `data`) |
| Place later WorkItems that reuse a volume workspace | Work Scheduler (ExecutionTarget that holds the volume) |
| Flag workspace access (`rw` / `ro` / `copy`); snapshot is the cross-cluster path | AO |
| Serialize dispatch per workspace id (volume RWO, or snapshot `rw`) | Work Scheduler |
| Hydrate / publish workspace snapshot (full tree to S3) | Worker Manager / SDK |
| Delete workspace (`DELETE` by id against EP) | AO |
| Purge workspace (TTL from last unmount) | Execution Plane |
| Map file ids to HTTP(S) URLs; run HTTP activity into `/workspace` | AO |
| Map repo + branch/tag to clone URL + SHA; run Git activity into `/workspace` | AO |
| Credential reference for Git remote (or HTTP if not presigned) | AO → Credential Provider |
| Mount workspace id at `/workspace`; inject artifact sidecar (producer HTTP server and/or consumer localhost client) | Worker Manager |
| Copy listed outputs aside, then unmount; S3 PUT from the copy (`status=uploading` → `available` or `failed`); does not gate the next WorkItem | Worker Manager |
| Write `artifacts[]` on `WorkItem.result` (UI); patch `status` when a PUT finishes or fails | Work Watcher / Work Store |
| Fetch listed outputs of a prior WorkItem when no shared volume | Same namespace: GET the producer sidecar HTTP server (spool). Else: consumer sidecar GETs S3 (holds credentials). |
| Match ExecutionTarget | First WorkItem: Reconciler (ignores `data`). Volume workspace reuse: Work Scheduler (ET that holds the volume). |

EP does not become a file manager. If the HTTP URL or Git remote is
unreachable from the ExecutionTarget, that fetch WorkItem fails. That
is a connectivity / credential problem, not a selector miss.

## Materialization (leaning)

The workspace is a volume on the ExecutionTarget. Object-store bytes
and Git trees arrive because an HTTP or Git activity wrote them
there. Listed outputs are **copied aside**, then uploaded to object
storage in the background from that copy. That PUT does not delay
the next WorkItem and does not read the live volume.

| Mechanism | Fits | Warm pool |
|---|---|---|
| **HTTP or Git activity** writing into `/workspace` | K8s and Podman (needs the workspace volume) | The activity itself yes; workspace is one holder per id |
| **Listed outputs** copied aside, then uploaded in the background | All backends (K8s, Podman, OpenShell) | Yes. Does not gate the next WorkItem. Consume via disk or sidecar |
| **Artifact sidecar** (WM-injected HTTP) | Producer: server on the original WorkItem (same namespace only, serves the spool). Consumer: localhost client to S3 when that server is unreachable. OpenShell: open. | Image stays dumb. S3 credentials stay in the sidecar. |
| **Workspace volume** (globally unique UUID, one ET) at `/workspace` | K8s PVC and Podman volume | One holder per id: concurrency 1 |
| **Workspace snapshot** (full tree to S3, hydrate anywhere) | All backends that can reach the bucket (incl. OpenShell) | `rw` serial; `ro` / `copy` may run in parallel |

OpenShell has no volume attach. Listed outputs still work. A shared
`/workspace` on OpenShell is the object-store snapshot path; HTTP
and Git activities cannot leave files for the next WorkItem via a
volume on that backend.

Leaning for MVP: **HTTP or Git activity + workspace volume** for
inbound files, **listed outputs** copied aside then uploaded in the
background. That listed-output PUT does not delay the next WorkItem.
A later node on the same UUID reads `/workspace`. A later node
without that volume calls the **Worker Manager sidecar**.
Object-store **workspace snapshot** is the alternative when AO needs
another cluster, parallel `ro` / `copy`, or OpenShell. The Worker
Manager attaches the workspace UUID at `/workspace`. It does not GET
object storage or clone Git as WorkItem **inputs**.

Because that volume is ReadWriteOnce, a second container cannot
mount the same id while the first WorkItem is running. Two different
ids are different volumes. That is not a per-WorkItem PVC create; it
is one id, one mount, one WorkItem.

[Example 02](examples/02-data-sharing-with-workspace.md) is the volume workspace,
not an input list. Workspace is at `/workspace` unless overridden.

## Sequence (workspace on one ExecutionTarget, two nodes)

```mermaid
sequenceDiagram
    participant AO as Automation Orchestrator
    participant WS as Work Store
    participant WM as Worker Manager
    participant Play as playbook
    participant Cons as consumer
    participant Side as sidecar
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
    WM->>Play: start with same workspace id at /workspace
    Play->>Vol: read /workspace/site.yml
    Play->>Vol: write /workspace/out/report.json
    Play-->>WM: exit
    WM->>WM: copy listed outputs aside
    Note over Vol: RW volume released; PUT reads the copy, not the live tree
    WM->>WS: result JSON + artifacts status=uploading. Next WorkItem can start
    WM->>S3: PUT from copy (background)

    AO->>WS: WorkItem C { no shared volume }
    WM->>Cons: start with sidecar on localhost
    Cons->>Side: GET artifact /workspace/out/report.json
    Side->>S3: GET (retry until available)
    WM->>WS: artifact status=available or failed (UI)
    Side-->>Cons: file bytes
```

## Out of scope

| Omitted | Why |
|---|---|
| Placement / selectors | [labels.md](labels.md) |
| Live PVC / Podman volume or disk capacity as a selector | Not a label. Open question in labels.md. |
| AO file upload, conversion, RBAC | [file-storage.md](../file-storage.md) |
| In-container activity SDK beyond curl/CLI to the sidecar | Separate SDK design. Sidecar HTTP is this contract. |
| Customer S3 IAM setup | Platform / credential work. Sidecar holds EP credentials; the activity image does not. |
| Git write-back (commit, push, PR) | Git activity is clone into `/workspace`. Writes stay on the volume or go to `outputs`. |
| Cross-target **volume** | A volume lives on exactly one ExecutionTarget. Cross-target: object-store snapshot, or use-case 2 via the sidecar. |
| Per-workspace size override | Size is the ExecutionTarget default. Not on the WorkItem. |
| `data.inputs` | Use a Git or HTTP WorkItem that writes into `/workspace`. |
| Streaming stdout as files | Still `WorkItem.result` / log plumbing |

## Open questions

1. **Sidecar transport.** Localhost HTTP is the contract. A CLI wraps
   that API. Exact routes, auth to the sidecar, and OpenShell (no
   sidecar) are implementation. Lean: HTTP on localhost, no S3 creds
   in the activity image.
2. **Credential reference shape.** Payload-level secret is wrong.
   HTTP and Git activities may take a Credential Provider id, or AO
   mints a presigned URL so an HTTP GET is unauthenticated. Listed
   output PUT/GET credentials stay in the sidecar.
3. **Failed runs and partial uploads.** Lean yes for listed
   `outputs`, so the author can inspect. Workspace files stay on the
   volume either way.
4. **Two workspace ids on one target at once.** Different volumes
   could in principle mount in parallel. Lean: serialize per id;
   two ids may run together if the target has capacity.
5. **OpenShell workspace.** No volume attach. Object-store snapshot
   (hydrate into the container), or no shared directory on that
   backend. HTTP and Git activities cannot leave files for the next
   WorkItem via a volume.
6. **Minted object-key scheme.** Work item id + basename is enough
    for uniqueness. Exact prefix (`artifacts/wi-…/`) is an
    implementation choice, not a payload field.
7. **Listed path missing after the run.** Omit from `artifacts`, or
    record an error for that path. Lean: omit, do not fail the whole
    upload list.
8. **Workspace snapshot format.** Tar blob vs key prefix per file;
   generation id on the WorkItem vs implicit "latest". Lean: one
   generation per exclusive `rw` exit; `ro` / `copy` pin that
   generation.
9. **When the snapshot PUT runs.** A cross-target successor must wait
   for `available`. Same-target volume successors do not. Whether the
   pack is Worker Manager after exit or a dedicated activity is
   open.

Git extras (submodules, LFS, sparse checkout, clone depth) and Git
credentials (HTTPS token vs SSH key) belong to the Git activity
Extension, not this contract.

## Coordination

- **[example 02](examples/02-data-sharing-with-workspace.md):** three WorkItems on
  one volume workspace at `/workspace`. The first places via
  selectors. Reuse pins B and C to that ExecutionTarget. The tree
  remains after each unmount.
- **[labels.md](labels.md):** HTTP and Git activity params and
  workspace UUID are not labels. Reuse of a volume workspace is a
  Work Scheduler placement constraint to the ExecutionTarget that
  holds the volume.
- **[Worker Manager](worker-manager.md):** looks up the workspace id,
  mounts its volume at `/workspace` (one RW mount per id); copies
  `data.outputs` aside, unmounts, uploads from the copy in the
  background. Injects the artifact sidecar: HTTP server on the
  producer WorkItem (same namespace, serves the spool) and localhost
  client on consumers that must GET S3. That PUT does not delay the
  next WorkItem. It does not GET object storage or clone Git as
  WorkItem inputs.
- **AAP-92722 (Work Scheduler):** after claim, if the workspace UUID
  already has a volume, dispatch to that ExecutionTarget. Do not
  dispatch a second **`rw`** WorkItem for a workspace id whose volume
  is still mounted. Snapshot `ro` / `copy` may overlap after that
  generation is `available`.
- **Workspace API:** AO mints the UUID on the WorkItem. EP creates
  the volume on the ExecutionTarget chosen for the first WorkItem
  that cites that id, after reconcile and before dispatch. AO does
  not pass a target. AO `DELETE`s by id. Size and TTL come from the
  ExecutionTarget. TTL (from last unmount) is an EP background task.
- **[Work Store](work-store.md):** `WorkItem.result` stays small JSON
  (run status plus `artifacts[]` UI metadata: minted `uri`, `status`
  `uploading` | `available` | `failed`, and `size` in bytes). Artifact
  bytes are not a JSONB column. EP patches `artifacts[].status` when a
  background PUT finishes or fails. Chaining does not poll this;
  the sidecar does.
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
  `/workspace`. Listed-output **fetch** is the Worker Manager sidecar:
  HTTP server on the producer WorkItem (same namespace) or localhost
  client to S3. Optional CLI wrapper. Harvest is copy-aside in the
  Worker Manager after exit, not an SDK inside the activity image.
