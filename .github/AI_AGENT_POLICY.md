# AI Agent Configuration Policy

This document records the upstream policy for AI coding-agent configuration in
this repository (Claude Code, Cursor, and similar tools that read project
instruction files). For the policy on AI-assisted **contributions** (disclosure,
accountability, quality standards), see
[`AI_POLICY.md`](AI_POLICY.md).

## Decision: no agent hooks in upstream

**Agent hooks are not allowed in the public / upstream tree.**

Executable agent hooks (for example Claude Code `hooks/` scripts wired through
`settings.json` / skill-trigger configs) were removed before publication. Those
hooks ran shell commands on tool-use and related agent events. That execution
model is a supply-chain risk: a compromised or poorly reviewed hook can run
arbitrary commands in a developer or CI environment with the privileges of the
agent session.

### What replaces hooks

There is **no hook-based enforcement** in upstream. The replacement is
**advisory project guidance**:

| Allowed upstream | Role |
| --- | --- |
| `CLAUDE.md`, `AGENTS.md`, and component `CLAUDE.md` / `AGENTS.md` | On-demand agent instructions |
| `.claude/skills/**` | Skill documents maintainers choose to ship |
| `.claude/commands/**` (when present) | Slash-command prompts as markdown |

Skills and commands are documentation loaded by the agent. They are **not**
executable hooks and must not invoke shell wrappers as part of agent lifecycle
events.

Local-only hook experiments (if any) stay on the contributor machine and must
never be committed.

## Private local agent settings

Local agent settings must not ship publicly. Root [`.gitignore`](../.gitignore)
ignores `.claude/*` by default and selectively un-ignores only the shared
skills (and commands, when present). In particular the following stay private:

- `.claude/settings.json` and `.claude/settings.local.json`
- `.claude/hooks/` and any other non-skill / non-command agent runtime files
- `CLAUDE.local.md`, `AGENTS.local.md`
- Editor/AI local dirs such as `.cursor/`, `.gemini/`

Do not force-add ignored agent settings or hooks in a pull request.

## Who may change `.claude/` and related agent docs

| Path | Ownership / review |
| --- | --- |
| This policy (`.github/AI_AGENT_POLICY.md`) | `@syntara-orchestration/syntara-leads` (see [CODEOWNERS](CODEOWNERS)) |
| Root / component `CLAUDE.md`, `AGENTS.md` | Same reviewers as the area of the change; treat policy-affecting edits as governance |
| `.claude/skills/**` | Owning product team per [CODEOWNERS](CODEOWNERS) (for example UX owns the PatternFly UX skill) |
| Re-introducing hooks or shipping `settings.json` | **Not permitted** under this policy. Requires an explicit policy revision reviewed by `@syntara-orchestration/syntara-leads` |

### Review bar for skill and instruction changes

Pull requests that change shared agent skills or instruction files should:

1. Keep content product-neutral and safe for a public repository (no internal
   hostnames, private Slack channels, credentials, or org-only runbooks).
2. Prefer linking to public docs over embedding internal process.
3. Stay advisory — do not add executable hook wiring.
4. Get review from the CODEOWNERS team for the touched paths.

## Decision: which skills stay in this repository

**This repository is the source of truth for the shared skills under
`.claude/skills/`.** They stay here so any contributor's agent can load them.
Do not remove them from this tree in favor of a private copy.

### The test (apply before adding or expanding a skill)

A skill belongs **in this public tree** if a contributor with only this
repository needs it to implement, test, or review correctly — and the text is
safe to publish.

A skill (or a section of a skill) must **stay out of this tree** if it contains
any of:

| Must not appear in `.claude/skills/` | Examples |
| --- | --- |
| Secret **values** | Passwords, tokens, API keys, cookie dumps |
| Org-only infrastructure | Internal hostnames, VPN-only URLs, private CI dashboards |
| Org-only process | Private chat channels, internal runbooks, org-only tracker IDs |
| Contributor machine paths | Home directories, local clone paths |
| Product overlay config | Private doc bases, branded URLs injected only on private builds |

### CRITICAL: secrets handling vs secret values

**Secret values must never appear in a skill.** How to *avoid leaking* a secret
**must** stay public, so agents working from this repo do not print
`SYNTARA_E2E_PASSWORD` or `cat` `backend/.secrets/admin-password`. See
[`.claude/skills/frontend-run-e2e/SKILL.md`](../.claude/skills/frontend-run-e2e/SKILL.md)
— that CRITICAL block is public on purpose.

Org-specific overlays (issue trackers, private MCP wiring, product doc URLs)
belong in **local** files this policy already ignores (`CLAUDE.local.md`,
`.claude/settings.local.json`) or in a private add-on that **adds** overlay
skills. That add-on must not become a second, independently edited copy of the
files below.

### Skills that stay in this repository

| Skill | Why public |
| --- | --- |
| `frontend-specialist` | Stack and workflow for this codebase |
| `frontend-coding-standards` | Patterns the code must follow |
| `frontend-patternfly-ux` | UX conventions for this UI |
| `frontend-testing-guidelines` | Vitest / accessibility |
| `frontend-playwright-e2e` | How to **write** E2E tests |
| `frontend-run-e2e` | How to **run** E2E tests, including never printing secrets |
| `frontend-pr-review` / `frontend-review-pr` | Review checklist |
| `frontend-build-ui-feature` | Feature wizard (tracker-neutral) |
| `frontend-library-references` | Public `llms.txt` URLs |
| `backend-fix-api-spec-drift` | Public OpenAPI workflow |

If a consumer vendors these files, re-copy from this repository after merge.
Do not edit the vendored copy as the source of truth.

## Related contributor docs

- Frontend AI workflow guide: [`frontend/docs/ai-assisted-development.md`](../frontend/docs/ai-assisted-development.md)
- Root agent entrypoints: [`CLAUDE.md`](../CLAUDE.md), [`AGENTS.md`](../AGENTS.md)
