#!/usr/bin/env node
import { checkPrTitle } from './lib/pr-title.js'

/** Escapes a message for use in a GitHub Actions workflow command. */
function escapeAnnotation(message: string): string {
  return message.replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A')
}

/** Checks the PR title from `PR_TITLE` and exits non-zero when it violates the format. */
function main(): void {
  /** Title of the pull request under review, passed via env to avoid shell injection. */
  const title = process.env.PR_TITLE
  if (title === undefined) {
    throw new Error('PR_TITLE is not set')
  }

  console.log(`PR title: ${title}`)
  const { errors, warnings, suggestion } = checkPrTitle(title)
  for (const warning of warnings) {
    console.log(`::warning title=PR title::${escapeAnnotation(warning)}`)
  }
  for (const error of errors) {
    console.log(`::error title=PR title::${escapeAnnotation(error)}`)
  }
  if (errors.length > 0) {
    if (suggestion) {
      console.log(`::notice title=Suggested PR title::${escapeAnnotation(suggestion)}`)
    }
    console.log('See "Commit Messages and PR Titles" in AGENTS.md for the required format.')
    process.exit(1)
  }
  console.log('✅ PR title follows the Conventional Commits format')
}

main()
