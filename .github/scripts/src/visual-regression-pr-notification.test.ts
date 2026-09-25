import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from './__tests__/setup.js'
import { notifyVisualRegressionBaseline } from './visual-regression-pr-notification.js'

describe('notifyVisualRegressionBaseline', () => {
  /** Fake Slack webhook URL used by MSW during notification tests. */
  const webhookUrl = 'https://hooks.example.com/visual-regression'

  /** Fake pull request URL expected in the Slack payload. */
  const prUrl = 'https://github.com/owner/repo/pull/42'

  it('posts the configured PR URL to the configured webhook', async () => {
    /** JSON body received by the MSW webhook handler. */
    let requestBody: unknown = null

    server.use(
      http.post(webhookUrl, async ({ request }) => {
        requestBody = await request.json()
        return HttpResponse.text('ok')
      })
    )

    await expect(
      notifyVisualRegressionBaseline({
        SLACK_VISUAL_REGRESSION_WEBHOOK_URL: webhookUrl,
        VISUAL_REGRESSION_PR_URL: prUrl,
      })
    ).resolves.toBe(true)

    expect(requestBody).toMatchObject({
      attachments: [
        {
          blocks: [
            {
              text: {
                text: expect.stringContaining(`<${prUrl}|Review PR>`),
              },
            },
          ],
        },
      ],
    })
  })

  it('skips when the Slack webhook is not configured', async () => {
    /** Tracks whether the notification attempted an HTTP request. */
    let requestReceived = false

    server.use(
      http.post(webhookUrl, () => {
        requestReceived = true
        return HttpResponse.text('ok')
      })
    )

    await expect(notifyVisualRegressionBaseline({ VISUAL_REGRESSION_PR_URL: prUrl })).resolves.toBe(false)

    expect(requestReceived).toBe(false)
  })

  it('fails when the PR URL is missing while Slack is configured', async () => {
    await expect(notifyVisualRegressionBaseline({ SLACK_VISUAL_REGRESSION_WEBHOOK_URL: webhookUrl })).rejects.toThrow(
      'VISUAL_REGRESSION_PR_URL is required'
    )
  })
})
