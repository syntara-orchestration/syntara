import { describe, expect, it, vi } from 'vitest'
import { notifyVisualRegressionBaseline } from './visual-regression-pr-notification.js'

describe('notifyVisualRegressionBaseline', () => {
  const webhookUrl = 'https://hooks.example.com/visual-regression'
  const prUrl = 'https://github.com/owner/repo/pull/42'

  it('passes the configured webhook and PR URL to the notifier', async () => {
    const sendVisualRegressionBaselineReady = vi.fn().mockResolvedValue(undefined)
    const createNotifier = vi.fn(() => ({ sendVisualRegressionBaselineReady }))

    await expect(
      notifyVisualRegressionBaseline(
        {
          SLACK_VISUAL_REGRESSION_WEBHOOK_URL: webhookUrl,
          VISUAL_REGRESSION_PR_URL: prUrl,
        },
        createNotifier
      )
    ).resolves.toBe(true)

    expect(createNotifier).toHaveBeenCalledWith(webhookUrl)
    expect(sendVisualRegressionBaselineReady).toHaveBeenCalledWith(prUrl)
  })

  it('skips when the Slack webhook is not configured', async () => {
    const createNotifier = vi.fn()

    await expect(notifyVisualRegressionBaseline({ VISUAL_REGRESSION_PR_URL: prUrl }, createNotifier)).resolves.toBe(
      false
    )

    expect(createNotifier).not.toHaveBeenCalled()
  })

  it('fails when the PR URL is missing while Slack is configured', async () => {
    const createNotifier = vi.fn()

    await expect(
      notifyVisualRegressionBaseline({ SLACK_VISUAL_REGRESSION_WEBHOOK_URL: webhookUrl }, createNotifier)
    ).rejects.toThrow('VISUAL_REGRESSION_PR_URL is required')

    expect(createNotifier).not.toHaveBeenCalled()
  })
})
