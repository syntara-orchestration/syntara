import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../__tests__/setup.js'
import { buildVisualRegressionBaselineReadyMessage, SlackNotifier } from '../slack.js'

describe('buildVisualRegressionBaselineReadyMessage', () => {
  it('builds a concise Slack review link', () => {
    const prUrl = 'https://github.com/owner/repo/pull/42'
    const message = buildVisualRegressionBaselineReadyMessage(prUrl)
    const [attachment] = message.attachments
    const [section] = attachment?.blocks ?? []

    expect(attachment?.blocks).toHaveLength(1)
    expect(section).toMatchObject({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `Visual regression baseline PR ready for review: <${prUrl}|Review PR>`,
      },
    })
    expect(JSON.stringify(message)).not.toContain(':eyes:')
  })
})

describe('SlackNotifier', () => {
  let notifier: SlackNotifier
  const webhookUrl = 'https://hooks.example.com/test-webhook'

  beforeEach(() => {
    notifier = new SlackNotifier(webhookUrl)
  })

  describe('sendVisualRegressionBaselineReady', () => {
    it('posts the review notification to the configured webhook', async () => {
      let requestReceived = false

      server.use(
        http.post(webhookUrl, () => {
          requestReceived = true
          return HttpResponse.text('ok')
        })
      )

      await notifier.sendVisualRegressionBaselineReady('https://github.com/owner/repo/pull/42')

      expect(requestReceived).toBe(true)
    })
  })
})
