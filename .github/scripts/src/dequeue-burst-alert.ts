#!/usr/bin/env node
import { GitHubClient } from './lib/github.js'
import { SlackNotifier } from './lib/slack.js'
import { getEnvironment } from './lib/env.js'
import { runScript } from './lib/run-script.js'
import { hasNewDequeueSince } from './lib/dequeue-state.js'

/** Number of dequeues within the time window that triggers an alert */
const DEQUEUE_THRESHOLD = 3

/** Time window in minutes for detecting dequeue bursts */
const TIME_WINDOW_MINUTES = 45

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

  const defaultBranch = await github.getDefaultBranch()
  console.log(`Monitoring dequeue activity for branch: ${defaultBranch}`)

  const currentEntries = await github.getMergeQueueEntries(defaultBranch)
  console.log(`Current queue depth: ${currentEntries.length}`)
  if (currentEntries.length === 0) {
    console.log('No alert needed (merge queue is empty)')
    return
  }

  const previousRuns = await github.getWorkflowRuns(
    'merge-queue-dequeue-alert.yml',
    new Date(Date.now() - TIME_WINDOW_MINUTES * 60 * 1000),
    env.runId,
    env.eventName
  )
  const previousRun = previousRuns[0]
  const timeWindowAgo = new Date(Date.now() - TIME_WINDOW_MINUTES * 60 * 1000)
  const recentDequeues = await github.getRecentDequeues(defaultBranch, timeWindowAgo)

  console.log(`Found ${recentDequeues.length} dequeued PRs in the last ${TIME_WINDOW_MINUTES} minutes`)

  if (recentDequeues.length > 0) {
    console.log('Recent dequeues:')
    recentDequeues.forEach((dequeue) =>
      console.log(`  - PR #${dequeue.number}: ${dequeue.title} (dequeued ${dequeue.dequeuedAt})`)
    )
  }

  // Alert if we see multiple dequeues (indicates systemic issue)
  const hasNewDequeue = hasNewDequeueSince(recentDequeues, previousRun ? new Date(previousRun.created_at) : undefined)

  if (recentDequeues.length < DEQUEUE_THRESHOLD || !hasNewDequeue) {
    console.log(
      `No alert needed (${recentDequeues.length} dequeues, ${currentEntries.length} queued, ` +
        `new event: ${hasNewDequeue}, threshold is ${DEQUEUE_THRESHOLD})`
    )
    return
  }

  console.log(`⚠️  ${recentDequeues.length} dequeues detected - potential systemic issue`)

  await slack.sendDequeueBurstAlert({
    dequeues: recentDequeues.map((dequeue) => ({
      number: dequeue.number,
      url: github.getPrUrl(dequeue.number),
      title: dequeue.title,
    })),
    timeWindowMinutes: TIME_WINDOW_MINUTES,
    queueUrl: github.getQueueUrl(defaultBranch),
  })

  console.log('✅ Alert sent to Slack')
}

runScript(main)
