/** Internal Jira project keys whose issue references must not appear in code, docs, or PR titles. */
export const JIRA_PROJECT_KEYS = ['AAP', 'ANSTRAT'] as const

/** Source of a regex matching one internal Jira issue key; a trailing `.digit` is excluded so versions like `AAP-2.5` don't match. */
export const JIRA_KEY_SOURCE = `\\b(?:${JIRA_PROJECT_KEYS.join('|')})-\\d+\\b(?!\\.\\d)`

/** Hosts of the internal Jira instance (current and legacy); the only place they appear in the repo. */
export const JIRA_HOSTS = ['redhat.atlassian.net', 'issues.redhat.com'] as const

/** Source of a regex matching an internal Jira browse URL on any of the Jira hosts. */
const JIRA_URL_SOURCE = `(?:https?://)?(?:${JIRA_HOSTS.map((host) => host.replace(/\./g, '\\.')).join('|')})/browse/[A-Z][A-Z0-9]*-\\d+`

/** Matches internal Jira browse URLs. */
const JIRA_URL_PATTERN = new RegExp(JIRA_URL_SOURCE, 'g')

/** Matches internal Jira issue keys and internal Jira browse URLs. */
const JIRA_REFERENCE_PATTERN = new RegExp(`${JIRA_URL_SOURCE}|${JIRA_KEY_SOURCE}`, 'g')

/** Returns every internal Jira reference found in the text, in order of appearance. */
export function findJiraReferences(text: string): string[] {
  return [...text.matchAll(JIRA_REFERENCE_PATTERN)].map((match) => match[0])
}

/** Returns every internal Jira browse URL found in the text, in order of appearance. */
export function findJiraUrls(text: string): string[] {
  return [...text.matchAll(JIRA_URL_PATTERN)].map((match) => match[0])
}

/** A line added by a diff, identified by its repo-relative path and new-file line number. */
export interface AddedLine {
  path: string
  line: number
  text: string
}

/** A Jira reference found on an added line. */
export interface JiraReferenceFinding extends AddedLine {
  references: string[]
}

/** Matches the new-file start line in a unified diff hunk header. */
const HUNK_HEADER_PATTERN = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/

/** Extracts added lines from `git diff` output, skipping file headers, removed lines, and deleted files. */
export function parseAddedLines(diff: string): AddedLine[] {
  /** Added lines collected across all files in the diff. */
  const added: AddedLine[] = []
  /** Path of the file currently being parsed, or null for deleted files. */
  let path: string | null = null
  /** Whether the parser is between `diff --git` and the first hunk, where `+++` is a header rather than content. */
  let inHeader = false
  /** New-file line number of the next added or context line. */
  let lineNumber = 0

  for (const raw of diff.split('\n')) {
    if (raw.startsWith('diff --git ')) {
      inHeader = true
      path = null
      continue
    }
    if (inHeader) {
      if (raw.startsWith('+++ ')) {
        const target = raw.slice(4)
        path = target === '/dev/null' ? null : target.replace(/^b\//, '')
      }
      const hunk = HUNK_HEADER_PATTERN.exec(raw)
      if (hunk) {
        inHeader = false
        lineNumber = Number(hunk[1])
      }
      continue
    }
    const hunk = HUNK_HEADER_PATTERN.exec(raw)
    if (hunk) {
      lineNumber = Number(hunk[1])
    } else if (raw.startsWith('+')) {
      if (path !== null) added.push({ path, line: lineNumber, text: raw.slice(1) })
      lineNumber++
    } else if (raw.startsWith(' ')) {
      lineNumber++
    }
  }
  return added
}

/** Paths allowed to contain Jira keys: docs and templates that describe this rule, this check's own tests, and generated files. */
export const JIRA_CHECK_EXCLUDED_PATHS: readonly RegExp[] = [
  /^(?:AGENTS|CLAUDE)\.md$/,
  /^docs\/contributing\.md$/,
  /^\.github\/pull_request_template\.md$/,
  /^\.github\/scripts\/src\/lib\/__tests__\/(?:jira|pr-title|pr-description)\.test\.ts$/,
  /(?:^|\/)(?:package-lock\.json|uv\.lock)$/,
]

/** Returns every non-excluded added line in the diff that contains an internal Jira reference. */
export function findJiraReferencesInDiff(
  diff: string,
  excludedPaths: readonly RegExp[] = JIRA_CHECK_EXCLUDED_PATHS
): JiraReferenceFinding[] {
  return parseAddedLines(diff)
    .filter(({ path }) => !excludedPaths.some((pattern) => pattern.test(path)))
    .map((line) => ({ ...line, references: findJiraReferences(line.text) }))
    .filter(({ references }) => references.length > 0)
}
