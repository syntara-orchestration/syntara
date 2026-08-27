#!/usr/bin/env node
import { GitHubClient } from './lib/github.js'
import { SlackNotifier } from './lib/slack.js'
import { getEnvironment } from './lib/env.js'
import { runScript } from './lib/run-script.js'

/** Number of dequeues within the time window that triggers an alert */
const DEQUEUE_THRESHOLD = 3

/** Time window in minutes for detecting dequeue bursts */
const TIME_WINDOW_MINUTES = 45
const POLL_INTERVAL_MINUTES = 15

/**
 * Detects dequeue bursts in the merge queue and sends Slack alerts.
 * Uses GitHub Timeline API to find actual removed_from_merge_queue events.
 * Alerts when multiple PRs are removed from the queue within the time window.
 */
async function main() {
  const env = getEnvironment()

  const github = new GitHubClient(env.githubToken, env.repository)
  const slack = new SlackNotifier(env.slackWebhookUrl)

  console.log('Checking for recent dequeue events...')

  // Fetch default branch dynamically
  const defaultBranch = await github.getDefaultBranch()
  console.log(`Monitoring dequeue activity for branch: ${defaultBranch}`)

  const currentEntries = await github.getMergeQueueEntries(defaultBranch)
  console.log(`Current queue depth: ${currentEntries.length}`)

  // Get PRs that were removed from the queue (actual dequeues, not merges)
  const timeWindowAgo = new Date(Date.now() - TIME_WINDOW_MINUTES * 60 * 1000)
  const recentDequeues = await github.getRecentDequeues(defaultBranch, timeWindowAgo)

  console.log(`Found ${recentDequeues.length} dequeued PRs in the last ${TIME_WINDOW_MINUTES} minutes`)

  if (recentDequeues.length > 0) {
    console.log('Recent dequeues:')
    recentDequeues.forEach((d) => console.log(`  - PR #${d.number}: ${d.title} (dequeued ${d.dequeuedAt})`))
  }

  // Alert if we see multiple dequeues (indicates systemic issue)
  const pollWindowAgo = new Date(Date.now() - POLL_INTERVAL_MINUTES * 60 * 1000)
  const hasNewDequeue = recentDequeues.some((dequeue) => new Date(dequeue.dequeuedAt) >= pollWindowAgo)

  if (recentDequeues.length < DEQUEUE_THRESHOLD || currentEntries.length === 0 || !hasNewDequeue) {
    console.log(
      `No alert needed (${recentDequeues.length} dequeues, ${currentEntries.length} queued, ` +
        `new event: ${hasNewDequeue}, threshold is ${DEQUEUE_THRESHOLD})`
    )
    return
  }

  console.log(`⚠️  ${recentDequeues.length} dequeues detected - potential systemic issue`)

  const queueUrl = github.getQueueUrl(defaultBranch)

  await slack.sendDequeueBurstAlert({
    dequeues: recentDequeues.map((d) => ({
      number: d.number,
      url: github.getPrUrl(d.number),
      title: d.title,
    })),
    timeWindowMinutes: TIME_WINDOW_MINUTES,
    queueUrl,
  })

  console.log('✅ Alert sent to Slack')
}

runScript(main)
