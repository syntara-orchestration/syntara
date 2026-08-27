#!/usr/bin/env node
import { SlackNotifier } from './lib/slack.js'
import { getEnvironment } from './lib/env.js'
import { runScript } from './lib/run-script.js'

/**
 * Sends the merge-queue backup (unhealthy) Slack alert.
 * Invoked by the "Send unhealthy alert" workflow step.
 */
async function main() {
  const env = getEnvironment()
  const slack = new SlackNotifier(env.slackWebhookUrl)

  const queueDepth = Number(process.env.QUEUE_DEPTH)
  const minutesSinceMerge = Number(process.env.MINUTES_SINCE_MERGE)
  const timeoutMinutes = Number(process.env.TIMEOUT_MINUTES)
  const queueUrl = process.env.QUEUE_URL

  if (
    !Number.isFinite(queueDepth) ||
    !Number.isFinite(minutesSinceMerge) ||
    !Number.isFinite(timeoutMinutes) ||
    !queueUrl
  ) {
    throw new Error('QUEUE_DEPTH, MINUTES_SINCE_MERGE, TIMEOUT_MINUTES, and QUEUE_URL are required')
  }

  await slack.sendQueueBackupAlert({
    queueDepth,
    minutesSinceMerge,
    timeoutMinutes,
    queueUrl,
  })

  console.log('✅ Unhealthy alert sent to Slack')
}

runScript(main)
