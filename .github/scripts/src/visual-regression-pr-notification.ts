#!/usr/bin/env node
import { SlackNotifier } from './lib/slack.js'

const webhookUrl = process.env.SLACK_VISUAL_REGRESSION_WEBHOOK_URL
const prUrl = process.env.VISUAL_REGRESSION_PR_URL

async function main(): Promise<void> {
  if (!webhookUrl) {
    console.log('SLACK_VISUAL_REGRESSION_WEBHOOK_URL is not configured; skipping notification')
    return
  }

  if (!prUrl) {
    throw new Error('VISUAL_REGRESSION_PR_URL is required when Slack notification is enabled')
  }

  await new SlackNotifier(webhookUrl).sendVisualRegressionBaselineReady(prUrl)
  console.log('✅ Visual regression baseline PR notification sent to Slack')
}

main().catch((error: unknown) => {
  console.error('Error:', error)
  process.exit(1)
})
