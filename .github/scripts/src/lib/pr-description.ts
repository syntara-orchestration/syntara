import { findJiraUrls } from './jira.js'

/** Matches any Jira issue key, e.g. in a `/browse/KEY-1` path or a `selectedIssue=KEY-1` query parameter. */
const ISSUE_KEY_PATTERN = /\b[A-Z][A-Z0-9]*-\d+\b/g

/** Returns errors for a PR description; Jira work items must be referenced by key, never by URL. */
export function checkPrDescription(body: string): string[] {
  return findJiraUrls(body).map((url) => {
    const key = url.match(ISSUE_KEY_PATTERN)?.at(-1)
    const replacement = key ? `the plain key ${key}` : 'the plain issue key'
    return `Jira URLs are not allowed in the PR description. Replace ${url} with ${replacement}.`
  })
}
