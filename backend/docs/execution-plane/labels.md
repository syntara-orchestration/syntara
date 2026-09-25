# Execution Plane: Labels and Work Selectors

The purpose of the Execution Plane (EP) label system, and how those
labels are used with Cluster and ExecutionTarget.

- Ticket: [AAP-92721](https://redhat.atlassian.net/browse/AAP-92721)
- Feature: [ANSTRAT-1803](https://redhat.atlassian.net/browse/ANSTRAT-1803)
- Parent epic: [AAP-82060](https://redhat.atlassian.net/browse/AAP-82060)
- Review discussion: [syntara#593](https://github.com/syntara-orchestration/syntara/pull/593)

## What this document is

The contract for **what labels mean** in the Execution Plane: what they
are for, what they are not for, who writes them, and how they meet
ExecutionTarget.

Matching, default routing, and ineligibility reasons live in the
[ExecutionTarget Reconciler](executiontarget-reconciler.md). This document does not
re-specify that algorithm. It exists because review of that design
showed the *vocabulary* and *ownership* of labels were still ambiguous.

Worked inventories (empty selectors, `region` / `env`, volume
mounts, OpenShell) are in [examples/](examples/). Key names in those
files are for readability; they are not the final field or label
vocabulary.

It does not specify Automation Orchestrator (AO) UI, Execution Profile
combination rules, or how Project / Workflow / Node objects store
affinity. Those are AO concerns. They must produce a single selector
map before work reaches EP; EP does not re-derive them.

## Purpose

Labels exist so work can be **routed to a place that can run it**.

ANSTRAT-1803 requires workload placement control: a workflow designer
directs a node to a capable execution-plane target (or group of
targets), and a platform administrator describes what each target
offers (region, cluster, isolation, GPU, and so on). The EP label
system is the shared language for that placement.

Two maps, same key-value shape:

| Map | Lives on | Meaning |
|---|---|---|
| **Labels** | Cluster and ExecutionTarget | Attributes the target **advertises**: "this is who I am / what I offer." |
| **Selectors** | Work (`WorkRequirements.selectors`) | Constraints the work **requires**: "I will only run where these keys match." |

The ExecutionTarget Reconciler treats work selectors as an exact AND
subset of the ExecutionTarget's **effective labels** (Cluster labels
with ExecutionTarget labels overlaid). That is the whole EP use of
the system.

Typical placement:

```
Work selectors { region: us-east-1 }
        │
        ▼  exact AND match
effective labels { region: us-east-1, gpu: true, ... }
        │   Cluster.labels ∪ ExecutionTarget.labels
        ▼
eligible ExecutionTarget set  →  Work Scheduler picks one
```

## Terminology

Do not call both sides "selectors." Review mixed those words; they are
not interchangeable.

| Term | Definition |
|---|---|
| **Label** | A `key → string value` advertised on a Cluster or ExecutionTarget. Extra labels on the target are allowed and do not rank it. |
| **Selector** | A `key → string value` required by a work item. Every requested key must exist on the target with that exact value. |
| **Natural label** | Written by provisioning / discovery from facts about the target (cluster type, cluster identity, observed region). |
| **User label** | Written by an administrator (or later a designer-facing control) to express intent the platform cannot infer. |
| **Reserved key** | A key the EP itself interprets. Default routing does **not** use a label; it uses `ExecutionTarget.is_default`. |

This is **not** the Syntara / AO `BaseResource.labels` column used for
list filters, RBAC policy, and resource tagging. See
[Relationship to AO resource labels](#relationship-to-ao-resource-labels).

## What labels are not

The label map is affinity metadata. It is a poor place for anything
that already has a typed field, changes independently of placement, or
requires the reconciler to understand live infrastructure.

| Do not encode as labels | Where it belongs | Why |
|---|---|---|
| Lifecycle (`active`, `degraded`, …) and `enabled` | Discrete fields on Cluster / ExecutionTarget; `IneligibilityReason` | A closed enum stays typed; stuffing status into labels loses that. |
| Live capacity, health, network reachability | Resource Monitor ([AAP-92724](https://redhat.atlassian.net/browse/AAP-92724)) | Eligibility that depends on current load is a filter, not a static advertisement. |
| Isolation / sandbox policy | Isolation Policy ([AAP-92726](https://redhat.atlassian.net/browse/AAP-92726)); work payload and target `default_policies` | Policy is not a key-value subset match. Extra sandbox constraints travel on the work payload; a target may hold baseline policy. See [example 03](examples/03-openshell-sandbox-policy.md). |
| Volume mounts, CPU/memory requests as *live* resources | Work payload / Worker Manager; Extension metadata | The reconciler must not inspect volume or network *state* of a target in order to match. Constructing the mount is execution, not placement. See [example 02](examples/02-volume-mount.md). |
| Default ExecutionTarget identity | `ExecutionTarget.is_default` | A boolean field, not a label. Empty work selectors take default routing. |
| Kubernetes pod template fields | Worker Manager / backend integration | Affinity labels are not copied onto pods unless a backend explicitly maps a reserved key. |
| AO object identity (project, workflow, node) as EP-interpreted keys | AO, when it builds the selector map | EP does not know what a Project is. AO *may* put `project_id=…` on work if an admin also labelled a target that way; EP still treats it as an opaque string match. |

## How labels get onto an ExecutionTarget

An ExecutionTarget (and its Cluster) only matches work if someone has
written the corresponding keys. Discovery cannot invent meaning from
an unlabeled host or cluster object.

### Natural labels (preferred for facts)

The canonical user story is "run this in `us-east-1`." Operators should
not have to type that by hand if provisioning already knows the
cluster's region, backend type, hostname, or id.

The Cluster / ExecutionTarget registry ([AAP-92716](https://redhat.atlassian.net/browse/AAP-92716))
and its provisioning path own **auto-labeling**. Natural labels are
facts about the target:

- backend / cluster type (for example `openshell`)
- concrete cluster identity (name, UUID, hostname)
- region or other topology the provisioner can observe

When those facts change, the provisioner may update them. It must not
clobber keys an administrator set. Matching does **not** distinguish
who wrote a key. A provisioned `region=us-east-1` and an admin
`region=us-east-1` are the same constraint. Labels are a single flat
map (see [Key format](#key-format)).

### User labels (intent the platform cannot infer)

An AO administrator sets the keys a target **supports** when the target
is registered or edited. Examples: `gpu=true`, `isolation=high`, a
customer-specific pool name. These are not derived from the backend's own tags (for example
Kubernetes `metadata.labels`) unless an operator (or a documented
mapping) put them there on purpose.

The UI does not have to expose a raw key-value editor. A control such
as "use this region for this workflow" can write selectors on the AO
side without showing the label system. UX is out of scope here.

### Cluster versus ExecutionTarget

A **Cluster** is one compute environment the Execution Plane can
schedule onto. The term is backend-agnostic: an OpenShift or Kubernetes
cluster, or a RHEL box running Podman, are all Clusters. An
**ExecutionTarget** is one place on that Cluster where work may run —
a Kubernetes namespace, the whole RHEL host, or another slice the
backend understands.

Labels that are true of the whole environment live on the Cluster
(region, cluster identity). Labels that are true of one place live on
the ExecutionTarget (`gpu=true`, `env=production`). The Cluster's
protected default is `is_default`, not a label.

Matching uses one map. For each ExecutionTarget the reconciler builds
**effective labels**: start from `Cluster.labels`, then overlay
`ExecutionTarget.labels`. Work selectors are tested against that
merged list only. A `region=us-east-1` label on the Cluster is
therefore visible on every ExecutionTarget in that Cluster; it does
not have to be copied onto each target. If both maps set the same
key, the ExecutionTarget value wins.

```
Cluster labels:          { region: us-east-1, cluster: prod-a }
ExecutionTarget labels:  { gpu: true }
effective labels:        { region: us-east-1, cluster: prod-a, gpu: true }
```

`cluster_type` and connection secrets stay discrete Cluster fields;
`backend_type` stays a discrete ExecutionTarget field. They are how
the Worker Manager is selected and how it connects, not how work is
matched. Copy the value onto labels when work must select a
non-default backend (for example `backend_type=openshell` in
[example 03](examples/03-openshell-sandbox-policy.md)). Matching still
uses the label map; the discrete field still selects the Worker
Manager after the target is chosen.

## How selectors get onto work

AO writes selectors when it submits work (Work Store /
[AAP-92720](https://redhat.atlassian.net/browse/AAP-92720)). The EP
never reads Project, Workflow, Node, or Execution Profile rows.

```
AO (author / settings / Extension)
  → resolve one selector map and a container image
  → WorkItem (selectors + payload.activity.image)
  → ExecutionTarget Reconciler (selectors only)
```

AO writes the container image on the work payload as
`activity.image`. That field is the image reference, not a node-type
alias such as `http_request`. AO resolved it from the Extension
registry ([ANSTRAT-2422](https://redhat.atlassian.net/browse/ANSTRAT-2422))
or from a user override of that image. EP does not consult the
registry.

Sources AO may combine **before** the selector map exists:

| Source | Typical keys | Notes |
|---|---|---|
| Execution Profile or node routing controls | `region`, `gpu`, similar | routing selectors as defined during PoC. |
| Future project / org / system defaults | same shape | Combination rules are an AO design. EP only sees the result. |

### What "global labels only" means

In the reconciler MVP, **EP matching is a single flat map**. There is
no EP hierarchy of organization → project → workflow → node.

That does **not** mean AO may only have system-wide affinity, and it
does not mean a global AO setting is AND-ed by EP with a later
per-project setting. If AO later has several levels, AO must document
how they combine (union, override, most-specific wins) and then send
EP one resolved selector map.

A required selector that no active ExecutionTarget satisfies leaves
the work unschedulable (`NO_MATCHING_TARGETS`). That is intended:
restrictive selectors are supposed to exclude targets that lack the
key. Defaults are not mixed into a selector match; see the
[ExecutionTarget Reconciler](executiontarget-reconciler.md#default-routing). Cold-start
fallback after a failed claim is a Work Scheduler concern
([AAP-92722](https://redhat.atlassian.net/browse/AAP-92722)).

## Matching against ExecutionTarget

Summary only; the algorithm is in the
[ExecutionTarget Reconciler](executiontarget-reconciler.md#selector-model).

1. Work selectors `{k: v}` match an ExecutionTarget if **every**
   requested key is present on that target's **effective labels**
   (Cluster labels, then ExecutionTarget labels) with that exact value.
2. Extra target labels do not help or hurt. Matching is boolean, not
   scored. The reconciler does not rank "best match."
3. Empty selectors take **default routing**, not "match every target."
4. MVP has no `In` / `NotIn` / existence operators and no preferred
   (soft) affinities. Preferred-then-sort is a later addition: still
   filter on required keys, then order in memory.

Every Cluster has a default ExecutionTarget (`is_default=True`). That
target is the cold-start fallback for the cluster. One default per
container image is **not** required; the default is image-agnostic
cold-start unless we later decide otherwise. The image is
`payload.activity.image` (already a container image reference), not a
required selector. See
[example 00](examples/00-one-workload-default-target.md).

Required selectors and the default target are in tension: a required
key the default does not carry will not select the default. Work then
stays pending (or fails as unschedulable) until a matching target
exists. That is a feature of required affinity, not a bug in default
routing.

## Key format

Exact vocabulary is not frozen. Keys are a single flat map of opaque
strings.

```
region = us-east-1
gpu    = true
cluster = local-openshift
```

The reconciler does not interpret key names. Default routing uses
`is_default`, not a reserved label. Cluster identity is a Cluster
label like any other; it is not a reserved matcher key.

The keys used in [examples/](examples/) (`region`, `env`,
`backend_type`, `cluster`) are readable stand-ins, not the final
names.

## Relationship to AO resource labels

Syntara resources (`Workflow`, `Project`, …) already have a `labels`
JSONB column: list filters (`?labels[env]=prod`), GIN indexes, and
authorization conditions. That system is documented in
[database.md](../standards/database.md) and
[api-response-format.md](../standards/api-response-format.md).

| | AO `BaseResource.labels` | EP Cluster / ExecutionTarget labels |
|---|---|---|
| Purpose | Tag, filter, and authorize AO objects | Advertise execution capacity for placement |
| Consumer | AO HTTP API, UI filters, policies | ExecutionTarget Reconciler |
| Empty map | Filter match-all | Work: default routing. Target: only empty work selectors can hit it via default routing |
| Schema | Syntara public resources | `execution_plane` Cluster / ExecutionTarget |

EP does not read AO resource labels. If a designer tags a workflow
`env=prod` and expects that to affect placement, AO must copy or map
that into `WorkRequirements.selectors` and an administrator must have
labelled an ExecutionTarget accordingly. There is no implicit join.


## Open questions

These are still design choices. They do not block documenting purpose
or the ExecutionTarget relationship above.

1. **Container image.** AO always puts the resolved image on
   `payload.activity.image`. The open question is whether that image is
   *also* a required selector (needed to pick a warm pool) or only a
   payload field (needed to cold-start). A required image selector
   excludes any default ExecutionTarget that does not advertise that
   image. A payload-only image means warm-pool matching needs another
   mechanism. Leaning: the Worker Manager *runs* `activity.image`;
   whether the reconciler *matches* on it is separate.
2. **Natural vs user storage.** Prefixes (`system/`, `user/`) are out
   for now: one flat `labels` map. Two fields merged at match time
   remains an option if provenance becomes a real problem.
3. **Preferred (soft) affinities.** Out of MVP. When they exist, they
   sort the eligible set; they do not change the boolean filter.
4. **AO combination rules** (system / project / workflow / node, and
   whether a lower level can unset a higher restriction). Required
   before AO exposes more than one layer. Not an EP matcher feature.
   Belongs in an AO integration document.
5. **Static capability labels** (for example "volume mounts supported")
   versus keeping capabilities entirely in the work payload. Do not
   model live resource availability as a selector.

## Coordination

- **[examples/](examples/):** concrete WorkItem, Cluster, and
  ExecutionTarget inventories for default routing, `region` / `env`,
  volume mounts, and OpenShell.
- **[ExecutionTarget Reconciler](executiontarget-reconciler.md):** matcher, default
  routing, lifecycle filter. Reads `ClusterSnapshot.labels` and
  `ExecutionTargetSnapshot.labels` as opaque `dict[str, str]`.
  Default routing uses `is_default`, not a label.
- **AAP-92716 (Cluster / ExecutionTarget Registry):** persist labels;
  auto-label on provision; preserve user keys when natural facts
  change.
- **AAP-92720 (Work Executor) / AAP-92715 (Work Store):** persist or
  map AO-resolved selectors into `WorkRequirements`; do not pass AO
  models into the reconciler.
- **AAP-92722 (Work Scheduler):** choose among eligible targets; may
  fall back to a cluster default after claim/provision failure.
- **AO integration (not an EP story):** Execution Profile, node routing
  controls, and any future multi-level combination. Produce one
  selector map. UX with product design (raw label editor is optional).
- **[kubernetes-backend.md](kubernetes-backend.md):** pod construction
  and claim use payload and backend config, not the affinity map,
  unless a reserved key is explicitly mapped.
