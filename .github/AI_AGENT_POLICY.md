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

## Related contributor docs

- Frontend AI workflow guide: [`frontend/docs/ai-assisted-development.md`](../frontend/docs/ai-assisted-development.md)
- Root agent entrypoints: [`CLAUDE.md`](../CLAUDE.md), [`AGENTS.md`](../AGENTS.md)
