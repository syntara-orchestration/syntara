#!/usr/bin/env node
import { pathToFileURL } from 'node:url'
import { SlackNotifier } from './lib/slack.js'

type VisualRegressionNotifier = Pick<SlackNotifier, 'sendVisualRegressionBaselineReady'>
type VisualRegressionNotifierFactory = (webhookUrl: string) => VisualRegressionNotifier
type VisualRegressionEnvironment = {
  SLACK_VISUAL_REGRESSION_WEBHOOK_URL?: string
  VISUAL_REGRESSION_PR_URL?: string
}

const processEnvironment: VisualRegressionEnvironment = {
  SLACK_VISUAL_REGRESSION_WEBHOOK_URL: process.env.SLACK_VISUAL_REGRESSION_WEBHOOK_URL,
  VISUAL_REGRESSION_PR_URL: process.env.VISUAL_REGRESSION_PR_URL,
}

export async function notifyVisualRegressionBaseline(
  env: VisualRegressionEnvironment = processEnvironment,
  createNotifier: VisualRegressionNotifierFactory = (webhookUrl) => new SlackNotifier(webhookUrl)
): Promise<boolean> {
  const webhookUrl = env.SLACK_VISUAL_REGRESSION_WEBHOOK_URL
  const prUrl = env.VISUAL_REGRESSION_PR_URL

  if (!webhookUrl) {
    console.log('SLACK_VISUAL_REGRESSION_WEBHOOK_URL is not configured; skipping notification')
    return false
  }

  if (!prUrl) {
    throw new Error('VISUAL_REGRESSION_PR_URL is required when Slack notification is enabled')
  }

  await createNotifier(webhookUrl).sendVisualRegressionBaselineReady(prUrl)
  return true
}

async function main(): Promise<void> {
  const sent = await notifyVisualRegressionBaseline()
  if (sent) {
    console.log('✅ Visual regression baseline PR notification sent to Slack')
  }
}

const entrypoint = process.argv[1]
if (entrypoint && import.meta.url === pathToFileURL(entrypoint).href) {
  main().catch((error: unknown) => {
    console.error('Error:', error)
    process.exit(1)
  })
}
