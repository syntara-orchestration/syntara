/** Block Kit element included in a Slack attachment. */
type SlackBlock = {
  type: string
  [key: string]: unknown
}

/** Color-coded Slack attachment containing Block Kit elements. */
type SlackAttachment = {
  color: string
  blocks: SlackBlock[]
}

/** Payload sent to a Slack incoming webhook. */
type SlackMessage = {
  attachments: SlackAttachment[]
}

/**
 * Builds the concise review message for a visual regression baseline PR.
 *
 * @param prUrl URL of the pull request that contains the updated baseline.
 * @returns Slack Block Kit payload linking to the pull request.
 */
export function buildVisualRegressionBaselineReadyMessage(prUrl: string): SlackMessage {
  return {
    attachments: [
      {
        color: '#36a64f',
        blocks: [
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: `Visual regression baseline PR ready for review: <${prUrl}|Review PR>`,
            },
          },
        ],
      },
    ],
  }
}

/**
 * Slack notification client using Block Kit formatted messages.
 */
export class SlackNotifier {
  /** Slack incoming webhook URL used for all notifications from this client. */
  private readonly webhookUrl: string

  /**
   * Creates a Slack notification client.
   *
   * @param webhookUrl Slack incoming webhook URL that receives notifications.
   */
  constructor(webhookUrl: string) {
    this.webhookUrl = webhookUrl
  }

  /**
   * Sends a concise review notification for the weekly visual regression PR.
   *
   * @param prUrl URL of the pull request that contains the updated baseline.
   */
  async sendVisualRegressionBaselineReady(prUrl: string): Promise<void> {
    await this.send(buildVisualRegressionBaselineReadyMessage(prUrl))
  }

  /**
   * Posts a Block Kit message to the configured Slack webhook.
   * Throws if the webhook request fails.
   */
  private async send(message: SlackMessage): Promise<void> {
    const response = await fetch(this.webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message),
    })

    if (!response.ok) {
      throw new Error(`Slack notification failed: ${response.status} ${response.statusText}`)
    }
  }
}
