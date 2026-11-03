import { pathToFileURL } from 'node:url'

/**
 * Scopes a visual-regression run to only the page-registry sections that a
 * given set of changed files could plausibly affect, so `/update-screenshots`
 * doesn't have to re-render all ~140 pages for a PR that only touches one
 * feature area.
 *
 * This is an ALLOWLIST, not a denylist: a changed file only narrows the run
 * if it matches one of the rules below. Anything unmatched — a shared
 * component, a hook, the mock API, the test infrastructure itself, or a
 * route directory we haven't accounted for — falls back to a full run.
 * Under-scoping (running too much) just costs CI minutes; over-scoping
 * (running too little) silently misses a page that needed a new baseline,
 * which is the failure mode this whole mechanism exists to avoid. When in
 * doubt, this file is written to be wrong in the "run more" direction.
 *
 * Backstop: even a wrong/incomplete rule below only causes staleness for at
 * most a week — the Monday cron (visual-regression-schedule.yml) always runs
 * every page against `devel` regardless of scoping, so any page this script
 * incorrectly excludes still gets caught and surfaced for uxd-team review on
 * the next weekly run.
 *
 * Several page-registry sections intentionally have NO scoped rule and can
 * only be reached via the full-run fallback:
 *   - `access-management/*` is one bucket, not sub-divided by section. Tab
 *     panels like RoleAssignmentsPanel.tsx and the roles/policies/assignments
 *     tests are rendered from shared code at the top of src/routes/access-management/,
 *     not from an isolated per-section folder — splitting it further risks
 *     silently excluding a page that shares that code.
 *   - `authentication` and `permission-gating` test cross-cutting RBAC/auth
 *     behavior that lives in the same shared access-management code.
 *   - `login` maps to the single file src/app/AppLogin.tsx.
 *
 * See VISUAL_REGRESSION.md's "Scoped /update-screenshots Runs" section for the
 * user-facing explanation of this behavior with examples.
 *
 * Usage:
 *   git diff --name-only <base> <head> | npm exec tsx -- scripts/visual-regression/scope-visual-regression.ts
 *
 * Output (stdout, exactly one line):
 *   SCOPE=NONE                    — no VR-relevant files changed; skip the run entirely
 *   SCOPE=FULL                    — at least one changed file isn't covered by a rule below
 *   SCOPE=<grep-extended-regex>   — safe to pass to `playwright test --grep`
 */

const ACCESS_MANAGEMENT_SECTIONS = [
  'access-management/assignments',
  'access-management/check-access',
  'access-management/groups',
  'access-management/policies',
  'access-management/projects',
  'access-management/roles',
  'access-management/service-accounts',
  'access-management/token-revocation',
  'access-management/users',
  'authentication',
  'permission-gating',
]

const CONFIGURATION_SECTIONS = ['configuration/credentials', 'configuration/integrations', 'settings']

// Ordered by specificity — first match wins for a given file. Prefixes are
// relative to `frontend/packages/syntara-ui/`.
const SCOPE_RULES: Array<{ prefix: string; sections: string[] }> = [
  { prefix: 'src/routes/workflows/', sections: ['workflows'] },
  { prefix: 'src/routes/builder/', sections: ['workflows'] },
  { prefix: 'src/routes/approvals/', sections: ['approvals'] },
  { prefix: 'src/routes/executions/', sections: ['executions'] },
  { prefix: 'src/routes/configuration/credentials/', sections: ['configuration/credentials'] },
  { prefix: 'src/routes/configuration/integrations/', sections: ['configuration/integrations'] },
  { prefix: 'src/routes/configuration/settings/', sections: ['settings'] },
  // Anything else directly under configuration/ (shared shell) — broaden to the whole group.
  { prefix: 'src/routes/configuration/', sections: CONFIGURATION_SECTIONS },
  { prefix: 'src/routes/documentation/', sections: ['support'] },
  // access-management is intentionally one bucket — see file header.
  { prefix: 'src/routes/access-management/', sections: ACCESS_MANAGEMENT_SECTIONS },
  { prefix: 'src/app/AppLogin.tsx', sections: ['login'] },
  { prefix: 'src/app/AppLogin.test.tsx', sections: ['login'] },
]

const SYNTARA_UI_PREFIX = 'frontend/packages/syntara-ui/'

/**
 * Repo-relative prefixes that can affect any VR page. Checked before the
 * syntara-ui-only filter so they force SCOPE=FULL instead of being dropped as
 * "outside syntara-ui" → SCOPE=NONE.
 */
const FULL_SUITE_PREFIXES = ['frontend/packages/syntara-mock-api/', 'frontend/packages/syntara-contracts/']

export type ScopeResult = { full: true } | { full: false; sections: string[] }

export function resolveScope(changedFiles: string[]): ScopeResult {
  const files = changedFiles.map((f) => f.trim()).filter((f) => f.length > 0)

  if (files.some((f) => FULL_SUITE_PREFIXES.some((prefix) => f.startsWith(prefix)))) {
    return { full: true }
  }

  const relevant = files.filter((f) => f.startsWith(SYNTARA_UI_PREFIX)).map((f) => f.slice(SYNTARA_UI_PREFIX.length))

  if (relevant.length === 0) {
    return { full: false, sections: [] }
  }

  const matchedSections = new Set<string>()

  for (const file of relevant) {
    const rule = SCOPE_RULES.find((r) => file.startsWith(r.prefix))
    if (!rule) {
      return { full: true }
    }
    for (const section of rule.sections) {
      matchedSections.add(section)
    }
  }

  return { full: false, sections: [...matchedSections] }
}

export function formatScopeLine(result: ScopeResult): string {
  if (result.full) {
    return 'SCOPE=FULL'
  }

  if (result.sections.length === 0) {
    return 'SCOPE=NONE'
  }

  // Test titles are `${section}/${name}` (see page-screenshots.spec.ts), but
  // Playwright's --grep matches the full title including the enclosing
  // describe block ("Page screenshots › <section>/<name>"), so `^` would
  // never match. Require the section to be preceded by whitespace (the
  // " › " separator) or true string start instead, so we don't accidentally
  // match a different section whose name happens to end with the same string.
  const escaped = result.sections.map((s) => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&'))
  return `SCOPE=(?:^|\\s)(${escaped.join('|')})/`
}

async function main() {
  const chunks: Buffer[] = []
  for await (const chunk of process.stdin) {
    chunks.push(chunk as Buffer)
  }
  const changedFiles = Buffer.concat(chunks)
    .toString('utf-8')
    .split('\n')
    .filter((line) => line.trim().length > 0)

  const result = resolveScope(changedFiles)

  if (result.full) {
    console.error('Scoping: at least one changed file is outside the known-safe allowlist — running the full suite.')
    console.log(formatScopeLine(result))
    return
  }

  if (result.sections.length === 0) {
    console.error('Scoping: no VR-relevant files changed — nothing to screenshot.')
    console.log(formatScopeLine(result))
    return
  }

  console.error(`Scoping: changed files map to section(s): ${result.sections.sort().join(', ')}`)
  console.log(formatScopeLine(result))
}

const entry = process.argv[1]
if (entry && import.meta.url === pathToFileURL(entry).href) {
  void main()
}
