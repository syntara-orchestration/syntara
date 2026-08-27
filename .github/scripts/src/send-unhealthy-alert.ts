#!/usr/bin/env node
import { SlackNotifier } from './lib/slack.js'
import { getUnhealthyAlertEnvironment } from './lib/env.js'
import { runScript } from './lib/run-script.js'

/**
 * Sends the merge-queue backup (unhealthy) Slack alert.
 * Invoked by the "Send unhealthy alert" workflow step.
 */
async function main() {
  const env = getUnhealthyAlertEnvironment()
  const slack = new SlackNotifier(env.slackWebhookUrl)

  await slack.sendQueueBackupAlert({
    queueDepth: env.queueDepth,
    minutesSinceMerge: env.minutesSinceMerge,
    timeoutMinutes: env.timeoutMinutes,
    queueUrl: env.queueUrl,
  })

  console.log('✅ Unhealthy alert sent to Slack')
}

runScript(main)
