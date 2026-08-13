# Software Bill of Materials (SBOM)

Container images built for this repository include an SBOM as part of the
Konflux build path. SBOM generation is **not** handled by GitHub Actions,
Renovate, or MintMaker.

## Produced by

Konflux Pipelines-as-Code (PAC) builds under [`.tekton/`](../.tekton/) invoke the
AAP Tekton catalog pipeline `build/container`
(`quay.io/aap-ci/tekton-catalog/pipeline/build/container`).

That catalog pipeline generates and publishes an SBOM by default (alongside the
image). PipelineRuns in this repo do **not** set `SKIP_SBOM_GENERATION`; leaving
the default keeps SBOM generation enabled.

Relevant examples:

- Backend push (devel): `.tekton/ansible-automation-orchestrator-backend-devel-push.yaml`
- UI push (devel): `.tekton/ansible-automation-orchestrator-ui-devel-push.yaml`
- Matching pull-request PipelineRuns under `.tekton/` for the same components

Built images are pushed to Quay under
`quay.io/redhat-user-workloads/nexus-tenant/ansible-automation-platform/`.

## Consumed by

| Consumer | How |
| --- | --- |
| **Conforma** (Enterprise Contract) | PR integration tests such as `conforma-on-pull-request-devel` verify image policy, including supply-chain metadata. GitHub CI waits on these checks via the Konflux gate jobs in `.github/workflows/ci-backend.yml` and `.github/workflows/ci-frontend.yml`. |
| **Konflux UI** | Open a successful component PipelineRun and use **View SBOM** to inspect the attached SBOM. |
| **`cosign download sbom`** | With registry credentials that can read the image: `cosign download sbom <image-ref>`. Prefer digest refs when available. |

## Not produced by

- **Renovate / MintMaker** — dependency update bots only; they do not generate or publish image SBOMs (`renovate.json` and MintMaker PRs are unrelated to this path).
- **GitHub Actions app CI** — lint, test, typecheck, and related workflows do not emit container SBOMs.

## How to verify

1. **Pipeline config (no auth):** Confirm `.tekton/` PipelineRuns reference
   `pipeline/build/container` and do not disable SBOM generation.
2. **Konflux UI:** After a successful image build, open the PipelineRun →
   **View SBOM**.
3. **CLI (requires Quay access):**

   ```bash
   cosign download sbom \
     quay.io/redhat-user-workloads/nexus-tenant/ansible-automation-platform/<image>@sha256:<digest>
   ```

   Registry access to `redhat-user-workloads` is restricted; unauthenticated
   downloads return `UNAUTHORIZED`.
