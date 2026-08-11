import type { Environment } from './types.js';

export function getEnvironment(): Environment {
  const githubToken = process.env.GITHUB_TOKEN;
  const slackWebhookUrl = process.env.SLACK_WEBHOOK_URL;
  const repository = process.env.GITHUB_REPOSITORY;
  const runId = process.env.GITHUB_RUN_ID;
  const headRef = process.env.GITHUB_HEAD_REF;

  if (!githubToken) {
    throw new Error('GITHUB_TOKEN environment variable is required');
  }

  if (!slackWebhookUrl) {
    throw new Error('SLACK_WEBHOOK_URL environment variable is required');
  }

  if (!repository) {
    throw new Error('GITHUB_REPOSITORY environment variable is required');
  }

  if (!runId) {
    throw new Error('GITHUB_RUN_ID environment variable is required');
  }

  return {
    githubToken,
    slackWebhookUrl,
    repository,
    runId: parseInt(runId, 10),
    headRef,
  };
}
