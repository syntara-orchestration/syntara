#!/usr/bin/env node
import { SlackNotifier } from './lib/slack.js'
import { getEnvironment } from './lib/env.js'
import { runScript } from './lib/run-script.js'

/**
 * Sends the merge-queue recovery Slack alert.
 * Invoked by the "Send recovery alert" workflow step.
 */
async function main() {
  const env = getEnvironment()
  const slack = new SlackNotifier(env.slackWebhookUrl)

  const queueUrl = process.env.QUEUE_URL
  if (!queueUrl) {
    throw new Error('QUEUE_URL is required')
  }

  await slack.sendQueueRecoveryAlert(queueUrl)
  console.log('✅ Recovery alert sent to Slack')
}

runScript(main)
