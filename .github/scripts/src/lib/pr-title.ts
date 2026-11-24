import { JIRA_KEY_SOURCE, findJiraReferences } from './jira.js'

/** Conventional Commits types accepted by the `conventional-pre-commit` hook. */
export const CONVENTIONAL_TYPES = [
  'feat',
  'fix',
  'docs',
  'style',
  'refactor',
  'perf',
  'test',
  'build',
  'ci',
  'chore',
  'revert',
] as const

/** Recommended maximum subject length; longer titles produce a warning, not a failure. */
export const MAX_TITLE_LENGTH = 72

/** Matches `<type>(<scope>)!: <description>` where scope and `!` are optional. */
const TITLE_PATTERN = /^(?<type>[a-z]+)(?:\((?<scope>[^()\s]+)\))?!?: (?<description>\S.*)$/

/** Outcome of checking a PR title; any error fails the check, warnings are advisory. */
export interface PrTitleCheckResult {
  errors: string[]
  warnings: string[]
  /** A corrected title, offered only when normalization produces a title with no errors. */
  suggestion?: string
}

/** Returns the errors and warnings for a title without computing a suggestion. */
function validatePrTitle(title: string): Omit<PrTitleCheckResult, 'suggestion'> {
  /** Problems that make the title invalid. */
  const errors: string[] = []
  /** Style issues that should be fixed but don't fail the check. */
  const warnings: string[] = []

  if (/[[\]]/.test(title)) {
    errors.push('Square brackets are not allowed. Use parentheses for the scope, e.g. `fix(auth): …`.')
  }
  const jiraReferences = findJiraReferences(title)
  if (jiraReferences.length > 0) {
    errors.push(
      `Jira references are not allowed in the title (found ${jiraReferences.join(', ')}). Reference the issue key in the PR description instead.`
    )
  }

  const match = TITLE_PATTERN.exec(title)
  if (!match?.groups) {
    if (/^[a-z]+\(\s*\)/.test(title)) {
      errors.push('The scope is empty. Drop the parentheses when there is no scope, e.g. `fix: …`.')
    } else {
      errors.push('The title must match `<type>(<scope>): <description>` (scope optional), e.g. `fix(auth): …`.')
    }
    return { errors, warnings }
  }

  const { type, description } = match.groups
  if (!(CONVENTIONAL_TYPES as readonly string[]).includes(type)) {
    errors.push(`Unknown type \`${type}\`. Use one of: ${CONVENTIONAL_TYPES.join(', ')}.`)
  }
  if (title.length > MAX_TITLE_LENGTH) {
    warnings.push(`The title is ${title.length} characters; keep it to ${MAX_TITLE_LENGTH} or fewer.`)
  }
  if (/^[A-Z][a-z]/.test(description)) {
    warnings.push('Start the description with a lowercase letter.')
  }
  if (description.endsWith('.')) {
    warnings.push('Drop the trailing period from the description.')
  }
  return { errors, warnings }
}

/** Matches a scope made up only of Jira keys, e.g. `(PROJ-123)` or `(PROJ-1, PROJ-2)` with a real project key. */
const JIRA_ONLY_SCOPE = new RegExp(`^([a-z]+)\\((?:${JIRA_KEY_SOURCE})(?:\\s*,\\s*(?:${JIRA_KEY_SOURCE}))*\\)`)

/** Matches a Jira key wrapped in brackets or parentheses anywhere in the title. */
const WRAPPED_JIRA_KEY = new RegExp(`\\s*[[(](?:${JIRA_KEY_SOURCE})[\\])]`, 'g')

/** Matches a Jira key used as a prefix of the description, e.g. `fix: PROJ-123 handle …`. */
const LEADING_JIRA_KEY = new RegExp(`^([a-z]+(?:\\([^()]*\\))?!?: )(?:${JIRA_KEY_SOURCE})\\s*[:-]?\\s*`)

/** Rewrites common title mistakes (bracket scopes, bracket tags, Jira keys, casing, spacing) into Conventional Commits form. */
export function normalizePrTitle(title: string): string {
  return (
    title
      .trim()
      .replace(/\s+/g, ' ')
      // fix[auth]: → fix(auth):
      .replace(/^([A-Za-z]+)\[([^\]]*)\]/, '$1($2)')
      // Leading tags such as "[UI] " or "[PROJ-123]: "
      .replace(/^(?:\[[^\]]*\]\s*)+:?\s*/, '')
      // Fix: → fix:
      .replace(/^([A-Za-z]+)(?=[(!:])/, (type) => type.toLowerCase())
      .replace(WRAPPED_JIRA_KEY, '')
      .replace(JIRA_ONLY_SCOPE, '$1')
      .replace(/^([a-z]+)\(\s*\)/, '$1')
      // fix(e2e):Unskip → fix(e2e): Unskip
      .replace(/^([a-z]+(?:\([^()]*\))?!?):(?=\S)/, '$1: ')
      .replace(LEADING_JIRA_KEY, '$1')
      .trim()
  )
}

/** Validates a PR title against the repository's Conventional Commits rules and suggests a fix when one is safe. */
export function checkPrTitle(title: string): PrTitleCheckResult {
  const result: PrTitleCheckResult = validatePrTitle(title)
  if (result.errors.length > 0) {
    const normalized = normalizePrTitle(title)
    if (normalized !== title && validatePrTitle(normalized).errors.length === 0) {
      result.suggestion = normalized
    }
  }
  return result
}
