#!/usr/bin/env node
import { execFileSync } from 'node:child_process'
import { findJiraReferencesInDiff } from './lib/jira.js'

/** Escapes a message for use in a GitHub Actions workflow command. */
function escapeAnnotation(message: string): string {
  return message.replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A')
}

/** Fails when lines added between `DIFF_BASE` and `DIFF_HEAD` contain internal Jira references. */
function main(): void {
  /** Base revision; on a `pull_request` checkout, `HEAD^1` is the target branch tip of the merge commit. */
  const base = process.env.DIFF_BASE || 'HEAD^1'
  /** Head revision containing the PR changes. */
  const head = process.env.DIFF_HEAD || 'HEAD'

  const diff = execFileSync(
    'git',
    ['-c', 'core.quotePath=false', 'diff', '--no-color', '--no-ext-diff', '--unified=0', base, head],
    { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 }
  )
  const findings = findJiraReferencesInDiff(diff)
  for (const { path, line, references } of findings) {
    const message = `Jira reference ${references.join(', ')} added. Explain the reason in plain language instead; reference the issue key in the PR description.`
    console.log(`::error file=${path},line=${line},title=Jira reference::${escapeAnnotation(message)}`)
  }
  if (findings.length > 0) {
    console.log(`Found Jira references on ${findings.length} added line(s).`)
    console.log('See "No Jira References in Code or Docs" in AGENTS.md.')
    process.exit(1)
  }
  console.log('✅ No Jira references in added lines')
}

main()
