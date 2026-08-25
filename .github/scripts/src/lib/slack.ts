type SlackBlock = {
  type: string;
  [key: string]: unknown;
};

type SlackAttachment = {
  color: string;
  blocks: SlackBlock[];
};

type SlackMessage = {
  attachments: SlackAttachment[];
};

/**
 * Slack notification client using Block Kit formatted messages.
 * Sends color-coded alerts for merge queue health events.
 */
export class SlackNotifier {
  private readonly webhookUrl: string;

  constructor(webhookUrl: string) {
    this.webhookUrl = webhookUrl;
  }

  /**
   * Sends a red alert when multiple PRs are dequeued in rapid succession.
   * Indicates a systemic issue causing repeated check failures.
   */
  async sendDequeueBurstAlert(params: {
    dequeues: Array<{ number: number; url: string; title: string }>;
    timeWindowMinutes: number;
    queueUrl: string;
  }): Promise<void> {
    const { dequeues, timeWindowMinutes, queueUrl } = params;

    const prLinks = dequeues
      .map((pr) => `<${pr.url}|#${pr.number}>`)
      .join(', ');

    const message: SlackMessage = {
      attachments: [
        {
          color: '#dc3545',
          blocks: [
            {
              type: 'header',
              text: {
                type: 'plain_text',
                text: '⚠️ Merge queue: multiple PRs ejected',
              },
            },
            {
              type: 'section',
              fields: [
                {
                  type: 'mrkdwn',
                  text: `*Dequeues in last ${timeWindowMinutes} min:* ${dequeues.length}`,
                },
                {
                  type: 'mrkdwn',
                  text: `*PRs:* ${prLinks}`,
                },
              ],
            },
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: 'Multiple PRs were removed from the merge queue due to failed checks. This may indicate a systemic issue.',
              },
            },
            {
              type: 'actions',
              elements: [
                {
                  type: 'button',
                  text: {
                    type: 'plain_text',
                    text: 'View Merge Queue',
                  },
                  url: queueUrl,
                },
              ],
            },
          ],
        },
      ],
    };

    await this.send(message);
  }

  /**
   * Sends a red alert when the merge queue has stalled.
   * Fires when PRs are waiting but nothing has merged beyond the timeout threshold.
   */
  async sendQueueBackupAlert(params: {
    queueDepth: number;
    minutesSinceMerge: number;
    timeoutMinutes: number;
    queueUrl: string;
  }): Promise<void> {
    const { queueDepth, minutesSinceMerge, timeoutMinutes, queueUrl } = params;
    const message: SlackMessage = {
      attachments: [
        {
          color: '#dc3545',
          blocks: [
            {
              type: 'header',
              text: {
                type: 'plain_text',
                text: '⚠️ Merge queue: backed up',
              },
            },
            {
              type: 'section',
              fields: [
                {
                  type: 'mrkdwn',
                  text: `*Queue depth:* ${queueDepth} PRs`,
                },
                {
                  type: 'mrkdwn',
                  text: `*Time since last merge:* ~${minutesSinceMerge} minutes`,
                },
              ],
            },
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: `The merge queue has entries but nothing has merged in over ${timeoutMinutes} minutes. The queue may be stalled.`,
              },
            },
            {
              type: 'actions',
              elements: [
                {
                  type: 'button',
                  text: {
                    type: 'plain_text',
                    text: 'View Merge Queue',
                  },
                  url: queueUrl,
                },
              ],
            },
          ],
        },
      ],
    };

    await this.send(message);
  }

  /**
   * Sends a green recovery notification when the merge queue resumes merging.
   * Fires when queue transitions from unhealthy back to healthy.
   */
  async sendQueueRecoveryAlert(queueUrl: string): Promise<void> {
    const message: SlackMessage = {
      attachments: [
        {
          color: '#28a745',
          blocks: [
            {
              type: 'header',
              text: {
                type: 'plain_text',
                text: '✅ Merge queue: recovered',
              },
            },
            {
              type: 'section',
              fields: [
                {
                  type: 'mrkdwn',
                  text: '*Incident duration:* ~5-10 minutes',
                },
                {
                  type: 'mrkdwn',
                  text: '*Status:* Merges resuming',
                },
              ],
            },
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: 'The merge queue has recovered and PRs are merging again.',
              },
            },
            {
              type: 'actions',
              elements: [
                {
                  type: 'button',
                  text: {
                    type: 'plain_text',
                    text: 'View Merge Queue',
                  },
                  url: queueUrl,
                },
              ],
            },
          ],
        },
      ],
    };

    await this.send(message);
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
    });

    if (!response.ok) {
      throw new Error(
        `Slack notification failed: ${response.status} ${response.statusText}`
      );
    }
  }
}
