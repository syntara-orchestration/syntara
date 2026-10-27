#!/usr/bin/env node
import { checkPrDescription } from './lib/pr-description.js'

/** Escapes a message for use in a GitHub Actions workflow command. */
function escapeAnnotation(message: string): string {
  return message.replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A')
}

/** Checks the PR description from `PR_BODY` and exits non-zero when it contains Jira URLs. */
function main(): void {
  /** Body of the pull request under review; empty when the PR has no description. */
  const body = process.env.PR_BODY ?? ''

  const errors = checkPrDescription(body)
  for (const error of errors) {
    console.log(`::error title=PR description::${escapeAnnotation(error)}`)
  }
  if (errors.length > 0) {
    console.log('See "No Jira References in Code or Docs" in AGENTS.md.')
    process.exit(1)
  }
  console.log('✅ PR description references Jira work items by key only')
}

main()
