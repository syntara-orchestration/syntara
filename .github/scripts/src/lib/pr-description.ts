import { findJiraUrls } from './jira.js'

/** Returns errors for a PR description; Jira work items must be referenced by key, never by URL. */
export function checkPrDescription(body: string): string[] {
  return findJiraUrls(body).map((url) => {
    const key = url.slice(url.lastIndexOf('/') + 1)
    return `Jira URLs are not allowed in the PR description. Replace ${url} with the plain key ${key}.`
  })
}
