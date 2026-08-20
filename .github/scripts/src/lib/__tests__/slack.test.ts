import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../__tests__/setup.js';
import { SlackNotifier } from '../slack.js';

describe('SlackNotifier', () => {
  let notifier: SlackNotifier;
  const webhookUrl = 'https://hooks.example.com/test-webhook';

  beforeEach(() => {
    notifier = new SlackNotifier(webhookUrl);
  });

  describe('sendDequeueBurstAlert', () => {
    it('sends a red alert with dequeue details', async () => {
      let requestBody: unknown = null;

      server.use(
        http.post(webhookUrl, async ({ request }) => {
          requestBody = await request.json();
          return HttpResponse.text('ok');
        })
      );

      await notifier.sendDequeueBurstAlert(
        3,
        '42',
        'https://github.com/owner/repo/pull/42',
        'https://github.com/owner/repo/queue/devel'
      );

      expect(requestBody).toMatchObject({
        attachments: [
          {
            color: '#dc3545',
            blocks: expect.arrayContaining([
              expect.objectContaining({
                type: 'header',
                text: expect.objectContaining({
                  text: expect.stringContaining('multiple PRs ejected'),
                }),
              }),
              expect.objectContaining({
                type: 'section',
                fields: expect.arrayContaining([
                  expect.objectContaining({
                    text: expect.stringContaining('3'),
                  }),
                  expect.objectContaining({
                    text: expect.stringContaining('#42'),
                  }),
                ]),
              }),
            ]),
          },
        ],
      });
    });

    it('throws when webhook returns non-200 status', async () => {
      server.use(
        http.post(webhookUrl, () => {
          return new HttpResponse(null, { status: 500 });
        })
      );

      await expect(
        notifier.sendDequeueBurstAlert(3, '42', 'https://pr', 'https://queue')
      ).rejects.toThrow('Slack notification failed: 500');
    });
  });

  describe('sendQueueBackupAlert', () => {
    it('sends a red alert with queue backup details', async () => {
      let requestBody: unknown = null;

      server.use(
        http.post(webhookUrl, async ({ request }) => {
          requestBody = await request.json();
          return HttpResponse.text('ok');
        })
      );

      await notifier.sendQueueBackupAlert(
        5,
        75,
        'https://github.com/owner/repo/queue/devel'
      );

      expect(requestBody).toMatchObject({
        attachments: [
          {
            color: '#dc3545',
            blocks: expect.arrayContaining([
              expect.objectContaining({
                type: 'header',
                text: expect.objectContaining({
                  text: expect.stringContaining('backed up'),
                }),
              }),
              expect.objectContaining({
                type: 'section',
                fields: expect.arrayContaining([
                  expect.objectContaining({
                    text: expect.stringContaining('5 PRs'),
                  }),
                  expect.objectContaining({
                    text: expect.stringContaining('75 minutes'),
                  }),
                ]),
              }),
            ]),
          },
        ],
      });
    });
  });

  describe('sendQueueRecoveryAlert', () => {
    it('sends a green recovery notification', async () => {
      let requestBody: unknown = null;

      server.use(
        http.post(webhookUrl, async ({ request }) => {
          requestBody = await request.json();
          return HttpResponse.text('ok');
        })
      );

      await notifier.sendQueueRecoveryAlert('https://github.com/owner/repo/queue/devel');

      expect(requestBody).toMatchObject({
        attachments: [
          {
            color: '#28a745',
            blocks: expect.arrayContaining([
              expect.objectContaining({
                type: 'header',
                text: expect.objectContaining({
                  text: expect.stringContaining('recovered'),
                }),
              }),
              expect.objectContaining({
                type: 'section',
                fields: expect.arrayContaining([
                  expect.objectContaining({
                    text: expect.stringContaining('Merges resuming'),
                  }),
                ]),
              }),
            ]),
          },
        ],
      });
    });
  });
});
