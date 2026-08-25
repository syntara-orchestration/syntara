import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse, graphql } from 'msw';
import { server } from '../../__tests__/setup.js';
import { GitHubClient } from '../github.js';

describe('GitHubClient', () => {
  let client: GitHubClient;

  beforeEach(() => {
    client = new GitHubClient('test-token', 'owner/repo');
  });

  describe('getWorkflowRuns', () => {
    it('fetches and validates workflow runs from GitHub API', async () => {
      const mockRuns = [
        {
          id: 123,
          name: 'Merge queue dequeue alert',
          status: 'completed',
          conclusion: 'success',
          created_at: '2026-08-11T10:00:00Z',
          html_url: 'https://github.com/owner/repo/actions/runs/123',
          head_branch: 'gh-readonly-queue/devel/pr-42-abc',
        },
        {
          id: 124,
          name: 'Merge queue dequeue alert',
          status: 'in_progress',
          conclusion: null,
          created_at: '2026-08-11T10:05:00Z',
          html_url: 'https://github.com/owner/repo/actions/runs/124',
          head_branch: 'gh-readonly-queue/devel/pr-43-def',
        },
      ];

      server.use(
        http.get('https://api.github.com/repos/owner/repo/actions/workflows/test.yml/runs', () => {
          return HttpResponse.json({
            total_count: 2,
            workflow_runs: mockRuns,
          });
        })
      );

      const since = new Date('2026-08-11T09:00:00Z');
      const runs = await client.getWorkflowRuns('test.yml', since);

      expect(runs).toHaveLength(1);
      expect(runs[0].id).toBe(123);
      expect(runs[0].status).toBe('completed');
    });

    it('excludes a specific run ID when provided', async () => {
      const mockRuns = [
        {
          id: 123,
          name: 'Test',
          status: 'completed',
          conclusion: 'success',
          created_at: '2026-08-11T10:00:00Z',
          html_url: 'https://github.com/owner/repo/actions/runs/123',
          head_branch: 'gh-readonly-queue/devel/pr-42-abc',
        },
        {
          id: 124,
          name: 'Test',
          status: 'completed',
          conclusion: 'success',
          created_at: '2026-08-11T10:05:00Z',
          html_url: 'https://github.com/owner/repo/actions/runs/124',
          head_branch: 'gh-readonly-queue/devel/pr-43-def',
        },
      ];

      server.use(
        http.get('https://api.github.com/repos/owner/repo/actions/workflows/test.yml/runs', () => {
          return HttpResponse.json({ total_count: 2, workflow_runs: mockRuns });
        })
      );

      const runs = await client.getWorkflowRuns('test.yml', new Date(), 123);

      expect(runs).toHaveLength(1);
      expect(runs[0].id).toBe(124);
    });
  });

  describe('getMergeQueueEntries', () => {
    it('fetches merge queue entries via GraphQL', async () => {
      const mockResponse = {
        data: {
          repository: {
            mergeQueue: {
              entries: {
                nodes: [
                  {
                    position: 1,
                    state: 'QUEUED',
                    enqueuedAt: '2026-08-11T10:00:00Z',
                    pullRequest: {
                      number: 42,
                      title: 'Fix the thing',
                    },
                  },
                  {
                    position: 2,
                    state: 'AWAITING_CHECKS',
                    enqueuedAt: '2026-08-11T10:05:00Z',
                    pullRequest: {
                      number: 43,
                      title: 'Add the feature',
                    },
                  },
                ],
              },
            },
          },
        },
      };

      server.use(
        graphql.operation(() => {
          return HttpResponse.json(mockResponse as any);
        })
      );

      const entries = await client.getMergeQueueEntries('devel');

      expect(entries).toHaveLength(2);
      expect(entries[0].position).toBe(1);
      expect(entries[0].pullRequest.number).toBe(42);
      expect(entries[1].position).toBe(2);
    });

    it('returns empty array when queue is null', async () => {
      server.use(
        graphql.operation(() => {
          return HttpResponse.json({
            data: { repository: { mergeQueue: null } },
          } as any);
        })
      );

      const entries = await client.getMergeQueueEntries('devel');

      expect(entries).toEqual([]);
    });
  });

  describe('getRecentCommits', () => {
    it('fetches commits created after a specific time', async () => {
      const mockCommits = [
        {
          sha: 'abc123',
          commit: {
            message: 'Merge PR #42',
            committer: {
              name: 'GitHub',
              date: '2026-08-11T10:00:00Z',
            },
          },
          html_url: 'https://github.com/owner/repo/commit/abc123',
        },
      ];

      server.use(
        http.get('https://api.github.com/repos/owner/repo/commits', () => {
          return HttpResponse.json(mockCommits);
        })
      );

      const since = new Date('2026-08-11T09:00:00Z');
      const commits = await client.getRecentCommits('devel', since);

      expect(commits).toHaveLength(1);
      expect(commits[0].sha).toBe('abc123');
      expect(commits[0].commit.message).toBe('Merge PR #42');
    });
  });

  describe('getWorkflowRunJobs', () => {
    it('fetches job details for a workflow run', async () => {
      const mockJobs = [
        {
          id: 1,
          name: 'check-queue-health',
          steps: [
            { name: 'Send unhealthy alert', conclusion: 'success' },
            { name: 'Send recovery alert', conclusion: 'skipped' },
          ],
        },
      ];

      server.use(
        http.get('https://api.github.com/repos/owner/repo/actions/runs/123/jobs', () => {
          return HttpResponse.json({ total_count: 1, jobs: mockJobs });
        })
      );

      const jobs = await client.getWorkflowRunJobs(123);

      expect(jobs).toHaveLength(1);
      expect(jobs[0].name).toBe('check-queue-health');
      expect(jobs[0].steps).toHaveLength(2);
    });
  });

  describe('getDefaultBranch', () => {
    it('fetches the default branch from repository info', async () => {
      server.use(
        http.get('https://api.github.com/repos/owner/repo', () => {
          return HttpResponse.json({
            name: 'repo',
            full_name: 'owner/repo',
            default_branch: 'devel',
          });
        })
      );

      const branch = await client.getDefaultBranch();

      expect(branch).toBe('devel');
    });

    it('handles repositories with main as default branch', async () => {
      server.use(
        http.get('https://api.github.com/repos/owner/repo', () => {
          return HttpResponse.json({
            name: 'repo',
            full_name: 'owner/repo',
            default_branch: 'main',
          });
        })
      );

      const branch = await client.getDefaultBranch();

      expect(branch).toBe('main');
    });
  });

  describe('getRecentDequeues', () => {
    it('returns PRs with removed_from_merge_queue events in the window', async () => {
      const since = new Date('2026-08-25T12:00:00Z');

      server.use(
        http.get('https://api.github.com/repos/owner/repo/pulls', ({ request }) => {
          const url = new URL(request.url);
          const state = url.searchParams.get('state');

          if (state === 'open') {
            return HttpResponse.json([
              {
                number: 10,
                title: 'Open dequeued PR',
                merged_at: null,
                updated_at: '2026-08-25T12:30:00Z',
              },
            ]);
          }

          return HttpResponse.json([
            {
              number: 11,
              title: 'Closed dequeued PR',
              merged_at: null,
              updated_at: '2026-08-25T12:20:00Z',
            },
            {
              number: 12,
              title: 'Successfully merged PR',
              merged_at: '2026-08-25T12:15:00Z',
              updated_at: '2026-08-25T12:15:00Z',
            },
          ]);
        }),
        http.get(
          'https://api.github.com/repos/owner/repo/issues/:number/timeline',
          ({ params }) => {
            const number = Number(params.number);

            if (number === 10) {
              return HttpResponse.json([
                {
                  event: 'removed_from_merge_queue',
                  created_at: '2026-08-25T12:10:00Z',
                },
                {
                  event: 'removed_from_merge_queue',
                  created_at: '2026-08-25T12:40:00Z',
                },
              ]);
            }

            if (number === 11) {
              return HttpResponse.json([
                {
                  event: 'removed_from_merge_queue',
                  created_at: '2026-08-25T12:05:00Z',
                },
              ]);
            }

            return HttpResponse.json([]);
          }
        )
      );

      const dequeues = await client.getRecentDequeues(since);

      expect(dequeues).toEqual([
        {
          number: 10,
          title: 'Open dequeued PR',
          dequeuedAt: '2026-08-25T12:40:00Z',
        },
        {
          number: 11,
          title: 'Closed dequeued PR',
          dequeuedAt: '2026-08-25T12:05:00Z',
        },
      ]);
    });

    it('skips merged PRs and dequeues outside the time window', async () => {
      const since = new Date('2026-08-25T12:00:00Z');

      server.use(
        http.get('https://api.github.com/repos/owner/repo/pulls', ({ request }) => {
          const state = new URL(request.url).searchParams.get('state');

          if (state === 'open') {
            return HttpResponse.json([
              {
                number: 20,
                title: 'Old dequeue',
                merged_at: null,
                updated_at: '2026-08-25T12:50:00Z',
              },
            ]);
          }

          return HttpResponse.json([
            {
              number: 21,
              title: 'Merged',
              merged_at: '2026-08-25T12:45:00Z',
              updated_at: '2026-08-25T12:45:00Z',
            },
          ]);
        }),
        http.get(
          'https://api.github.com/repos/owner/repo/issues/20/timeline',
          () => {
            return HttpResponse.json([
              {
                event: 'removed_from_merge_queue',
                created_at: '2026-08-25T11:00:00Z',
              },
              {
                event: 'commented',
                created_at: '2026-08-25T12:30:00Z',
              },
            ]);
          }
        )
      );

      const dequeues = await client.getRecentDequeues(since);

      expect(dequeues).toEqual([]);
    });

    it('continues when timeline fetch fails for a PR', async () => {
      const since = new Date('2026-08-25T12:00:00Z');

      server.use(
        http.get('https://api.github.com/repos/owner/repo/pulls', ({ request }) => {
          const url = new URL(request.url);
          if (url.searchParams.get('state') === 'open') {
            return HttpResponse.json([
              { number: 30, title: 'Fails timeline', merged_at: null },
              { number: 31, title: 'Ok dequeue', merged_at: null },
            ]);
          }
          return HttpResponse.json([]);
        }),
        http.get(
          'https://api.github.com/repos/owner/repo/issues/30/timeline',
          () => HttpResponse.json({ message: 'Not Found' }, { status: 404 })
        ),
        http.get(
          'https://api.github.com/repos/owner/repo/issues/31/timeline',
          () =>
            HttpResponse.json([
              {
                event: 'removed_from_merge_queue',
                created_at: '2026-08-25T12:10:00Z',
              },
            ])
        )
      );

      const dequeues = await client.getRecentDequeues(since);

      expect(dequeues).toEqual([
        {
          number: 31,
          title: 'Ok dequeue',
          dequeuedAt: '2026-08-25T12:10:00Z',
        },
      ]);
    });
  });

  describe('URL builders', () => {
    it('builds merge queue URL', () => {
      const url = client.getQueueUrl('devel');
      expect(url).toBe('https://github.com/owner/repo/queue/devel');
    });

    it('builds PR URL', () => {
      const url = client.getPrUrl(42);
      expect(url).toBe('https://github.com/owner/repo/pull/42');
    });
  });
});
