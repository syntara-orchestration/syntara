# Secrets Storage Strategy

Org-level vs repo-level secrets decision for the `syntara-orchestration` GitHub
organization, following the ansible-ui team pattern of distinct secrets per
environment.

---

## Decision

Secrets used across multiple repositories in the org are stored at **org level**
with repository access policies restricting which repos can read them. Secrets
specific to a single repo's tooling (e.g., a per-repo SonarCloud project token)
are stored at **repo level**.

---

## Storage Map

### Org-Level Secrets

| Secret | Rationale | Repository Access |
|--------|-----------|-------------------|
| `RH_REGISTRY_USER` | Same Red Hat registry credentials for all repos | All repos that build from `registry.redhat.io` base images |
| `RH_REGISTRY_TOKEN` | Paired with `RH_REGISTRY_USER` | Same as above |
| `QUAY_TOKEN` | Quay.io robot account for image publishing | Repos that publish container images |
| `SNYK_TOKEN` | Snyk organization token for security scanning | All repos with security scanning |

### Org-Level Variables

| Variable | Rationale | Repository Access |
|----------|-----------|-------------------|
| `QUAY_ROBOT_USERNAME` | Paired with `QUAY_TOKEN` | Same as `QUAY_TOKEN` |
| `SONAR_ORG` | Same SonarCloud organization for all repos | All repos with SonarCloud |

### Repo-Level Secrets (on `syntara-orchestration/syntara`)

| Secret | Rationale |
|--------|-----------|
| `SONAR_TOKEN` | Per-repo SonarCloud project token |
| `OPENROUTER_API_KEY` | Only this repo has LLM integration tests |
| `CURRENTS_PROJECT_ID` | Per-repo Currents.dev project |
| `CURRENTS_RECORD_KEY` | Per-repo Currents.dev recording |
| `CURRENTS_API_KEY` | Per-repo Currents.dev API access |
| `RAPIDAST_GCP_KEY` | Only this repo runs DAST scans |

### Repo-Level Variables (on `syntara-orchestration/syntara`)

| Variable | Rationale |
|----------|-----------|
| `SONAR_TOKEN_SECRET_NAME` | Different SonarCloud project key per repo |
| `SONAR_PROJECT_KEY_BACKEND` | Backend-specific SonarCloud project |
| `SONAR_PROJECT_KEY_FRONTEND` | Frontend-specific SonarCloud project |

---

## Repository Access Policies

For org-level secrets, use GitHub's "Repository access" setting to restrict
which repos can read each secret:

1. **Default**: "Selected repositories" (not "All repositories")
2. **Add only repos that need each secret** — don't blanket-grant access
3. **Review access when adding new repos** to the org
