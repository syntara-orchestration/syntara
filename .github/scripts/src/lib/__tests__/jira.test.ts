import { describe, it, expect } from 'vitest'
import { JIRA_HOSTS, findJiraReferences, findJiraReferencesInDiff, parseAddedLines } from '../jira.js'

/** Current and legacy Jira hosts; tests build URLs from them so the repo holds no literal Jira URL. */
const [jiraHost, legacyJiraHost] = JIRA_HOSTS

describe('findJiraReferences', () => {
  it.each([
    ['# Workaround for AAP-12345', ['AAP-12345']],
    ['// see ANSTRAT-1934 and AAP-1', ['ANSTRAT-1934', 'AAP-1']],
    [`See https://${legacyJiraHost}/browse/AAP-99105`, [`https://${legacyJiraHost}/browse/AAP-99105`]],
    [`See https://${jiraHost}/browse/AAP-99723`, [`https://${jiraHost}/browse/AAP-99723`]],
    [`link: ${legacyJiraHost}/browse/OTHER-7`, [`${legacyJiraHost}/browse/OTHER-7`]],
  ])('finds references in %s', (text, expected) => {
    expect(findJiraReferences(text)).toEqual(expected)
  })

  it.each([
    'Handle Jira webhook payloads',
    'Supported on AAP-2.5 and later',
    'Fixes CVE-2026-59869',
    'Encode as UTF-8 and hash with SHA-256',
    'aap-12345 branch',
    'XAAP-123 is not a project key',
    'https://jira.example.com/browse/PROJ-1',
  ])('ignores %s', (text) => {
    expect(findJiraReferences(text)).toEqual([])
  })
})

/** Unified diff covering an added file, a modified file, a deleted file, and a `+++`-looking added line. */
const SAMPLE_DIFF = [
  'diff --git a/backend/new.py b/backend/new.py',
  'new file mode 100644',
  'index 0000000..1111111',
  '--- /dev/null',
  '+++ b/backend/new.py',
  '@@ -0,0 +1,2 @@',
  '+# Workaround for AAP-12345',
  '+value = 1',
  'diff --git a/frontend/app.ts b/frontend/app.ts',
  'index 2222222..3333333 100644',
  '--- a/frontend/app.ts',
  '+++ b/frontend/app.ts',
  '@@ -10 +10 @@ export function app() {',
  '-  // TODO(AAP-1): remove',
  '+  // TODO: remove once the API returns ids',
  '@@ -40,0 +41,2 @@',
  '+++ b/not-a-header AAP-777',
  '+  return ANSTRAT-1934',
  'diff --git a/docs/old.md b/docs/old.md',
  'deleted file mode 100644',
  '--- a/docs/old.md',
  '+++ /dev/null',
  '@@ -1 +0,0 @@',
  '-AAP-5',
  'diff --git a/AGENTS.md b/AGENTS.md',
  '--- a/AGENTS.md',
  '+++ b/AGENTS.md',
  '@@ -5,0 +6 @@',
  '+- Never write `# Workaround for AAP-12345`.',
  '',
].join('\n')

describe('parseAddedLines', () => {
  it('returns added lines with new-file line numbers and skips headers and deletions', () => {
    expect(parseAddedLines(SAMPLE_DIFF)).toEqual([
      { path: 'backend/new.py', line: 1, text: '# Workaround for AAP-12345' },
      { path: 'backend/new.py', line: 2, text: 'value = 1' },
      { path: 'frontend/app.ts', line: 10, text: '  // TODO: remove once the API returns ids' },
      { path: 'frontend/app.ts', line: 41, text: '++ b/not-a-header AAP-777' },
      { path: 'frontend/app.ts', line: 42, text: '  return ANSTRAT-1934' },
      { path: 'AGENTS.md', line: 6, text: '- Never write `# Workaround for AAP-12345`.' },
    ])
  })

  it('counts context lines when the diff has them', () => {
    const diff = [
      'diff --git a/a.py b/a.py',
      '--- a/a.py',
      '+++ b/a.py',
      '@@ -1,2 +1,3 @@',
      ' one',
      '-two',
      '+2',
      ' three',
    ].join('\n')

    expect(parseAddedLines(diff)).toEqual([{ path: 'a.py', line: 2, text: '2' }])
  })
})

describe('findJiraReferencesInDiff', () => {
  it('reports added lines with Jira references outside excluded paths', () => {
    expect(findJiraReferencesInDiff(SAMPLE_DIFF)).toEqual([
      { path: 'backend/new.py', line: 1, text: '# Workaround for AAP-12345', references: ['AAP-12345'] },
      { path: 'frontend/app.ts', line: 41, text: '++ b/not-a-header AAP-777', references: ['AAP-777'] },
      { path: 'frontend/app.ts', line: 42, text: '  return ANSTRAT-1934', references: ['ANSTRAT-1934'] },
    ])
  })

  it('honors a custom exclusion list', () => {
    expect(findJiraReferencesInDiff(SAMPLE_DIFF, [/^(?:backend|frontend)\//])).toEqual([
      {
        path: 'AGENTS.md',
        line: 6,
        text: '- Never write `# Workaround for AAP-12345`.',
        references: ['AAP-12345'],
      },
    ])
  })
})
