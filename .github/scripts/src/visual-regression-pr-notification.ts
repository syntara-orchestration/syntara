#!/usr/bin/env node
import { pathToFileURL } from 'node:url'
import { SlackNotifier } from './lib/slack.js'

/** Environment variables used to send a visual regression baseline notification. */
type VisualRegressionEnvironment = {
  SLACK_VISUAL_REGRESSION_WEBHOOK_URL?: string
  VISUAL_REGRESSION_PR_URL?: string
}

/** Captures the process environment used by the command-line entrypoint. */
const processEnvironment: VisualRegressionEnvironment = {
  SLACK_VISUAL_REGRESSION_WEBHOOK_URL: process.env.SLACK_VISUAL_REGRESSION_WEBHOOK_URL,
  VISUAL_REGRESSION_PR_URL: process.env.VISUAL_REGRESSION_PR_URL,
}

/**
 * Sends the visual regression baseline PR notification when configured.
 *
 * @param env Environment values controlling whether and where to send the notification.
 * @returns `true` when a notification is sent, or `false` when Slack is not configured.
 * @throws If Slack is configured without a visual regression pull request URL.
 */
export async function notifyVisualRegressionBaseline(
  env: VisualRegressionEnvironment = processEnvironment
): Promise<boolean> {
  /** Slack incoming webhook URL configured for visual regression notifications. */
  const webhookUrl = env.SLACK_VISUAL_REGRESSION_WEBHOOK_URL

  /** Pull request URL included in the review notification. */
  const prUrl = env.VISUAL_REGRESSION_PR_URL

  if (!webhookUrl) {
    console.log('SLACK_VISUAL_REGRESSION_WEBHOOK_URL is not configured; skipping notification')
    return false
  }

  if (!prUrl) {
    throw new Error('VISUAL_REGRESSION_PR_URL is required when Slack notification is enabled')
  }

  await new SlackNotifier(webhookUrl).sendVisualRegressionBaselineReady(prUrl)
  return true
}

/** Runs the visual regression notification command and reports whether it sent a message. */
async function main(): Promise<void> {
  /** Indicates whether the notification was sent rather than skipped. */
  const sent = await notifyVisualRegressionBaseline()
  if (sent) {
    console.log('✅ Visual regression baseline PR notification sent to Slack')
  }
}

/** Absolute path of the current Node.js entrypoint, when this module is run directly. */
const entrypoint = process.argv[1]
if (entrypoint && import.meta.url === pathToFileURL(entrypoint).href) {
  main().catch((error: unknown) => {
    console.error('Error:', error)
    process.exit(1)
  })
}
