import { beforeAll, afterEach, afterAll } from 'vitest';
import { http, HttpResponse, graphql } from 'msw';
import { setupServer } from 'msw/node';

/**
 * Mock environment variables for tests.
 * These match the GitHub Actions context that the scripts expect.
 * Values are intentionally fake to avoid triggering security scanners.
 */
const mockEnv = {
  GITHUB_TOKEN: 'test-token-not-real',
  SLACK_CI_MONITORING_WEBHOOK_URL: 'https://hooks.example.com/slack-webhook-test',
  GITHUB_REPOSITORY: 'owner/repo',
  GITHUB_RUN_ID: '12345',
  GITHUB_HEAD_REF: 'gh-readonly-queue/devel/pr-42-abc123',
};

/**
 * MSW request handlers for GitHub and Slack APIs.
 * Tests can override these with custom handlers as needed.
 */
export const handlers = [
  // GitHub REST API - workflow runs
  http.get('https://api.github.com/repos/:owner/:repo/actions/workflows/:workflow/runs', () => {
    return HttpResponse.json({
      total_count: 0,
      workflow_runs: [],
    });
  }),

  // GitHub REST API - workflow run jobs
  http.get('https://api.github.com/repos/:owner/:repo/actions/runs/:runId/jobs', () => {
    return HttpResponse.json({
      total_count: 0,
      jobs: [],
    });
  }),

  // GitHub REST API - commits
  http.get('https://api.github.com/repos/:owner/:repo/commits', () => {
    return HttpResponse.json([]);
  }),

  // GitHub GraphQL API - merge queue (use operation() for anonymous queries)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  graphql.operation((): any => {
    return HttpResponse.json({
      data: {
        repository: {
          mergeQueue: null,
        },
      },
    });
  }),

  // Slack webhook (using example.com to avoid triggering security scanners)
  http.post('https://hooks.example.com/*', () => {
    return HttpResponse.text('ok');
  }),
];

export const server = setupServer(...handlers);

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
  // Set up mock environment variables for all tests
  Object.assign(process.env, mockEnv);
});

afterEach(() => {
  server.resetHandlers();
});

afterAll(() => server.close());
