#!/usr/bin/env node
import { notifyVisualRegressionBaseline } from './lib/visual-regression.js'

/** Runs the visual regression notification command and reports whether it sent a message. */
async function main(): Promise<void> {
  /** Indicates whether the notification was sent rather than skipped. */
  const sent = await notifyVisualRegressionBaseline()
  if (sent) {
    console.log('✅ Visual regression baseline PR notification sent to Slack')
  }
}

main().catch((error: unknown) => {
  console.error('Error:', error)
  process.exit(1)
})
