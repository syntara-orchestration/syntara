import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { getEnvironment } from '../env.js';

describe('getEnvironment', () => {
  let originalEnv: NodeJS.ProcessEnv;

  beforeEach(() => {
    // Snapshot current env (which includes setup.ts mock values)
    originalEnv = { ...process.env };
  });

  afterEach(() => {
    // Restore to snapshot
    process.env = originalEnv;
  });

  it('returns validated environment when all required vars are present', () => {
    process.env.GITHUB_TOKEN = 'test-token';
    process.env.SLACK_CI_MONITORING_WEBHOOK_URL = 'https://hooks.example.com/test-webhook';
    process.env.GITHUB_REPOSITORY = 'owner/repo';
    process.env.GITHUB_RUN_ID = '12345';
    process.env.GITHUB_HEAD_REF = 'gh-readonly-queue/devel/pr-123-abc';

    const env = getEnvironment();

    expect(env).toEqual({
      githubToken: 'test-token',
      slackWebhookUrl: 'https://hooks.example.com/test-webhook',
      repository: 'owner/repo',
      runId: 12345,
      headRef: 'gh-readonly-queue/devel/pr-123-abc',
    });
  });

  it('throws when GITHUB_TOKEN is missing', () => {
    delete process.env.GITHUB_TOKEN;
    process.env.SLACK_CI_MONITORING_WEBHOOK_URL = 'https://hooks.example.com/test';
    process.env.GITHUB_REPOSITORY = 'owner/repo';
    process.env.GITHUB_RUN_ID = '12345';

    expect(() => getEnvironment()).toThrow('Environment validation failed');
    expect(() => getEnvironment()).toThrow('githubToken');
  });

  it('throws when SLACK_CI_MONITORING_WEBHOOK_URL is missing', () => {
    process.env.GITHUB_TOKEN = 'test-token';
    delete process.env.SLACK_CI_MONITORING_WEBHOOK_URL;
    process.env.GITHUB_REPOSITORY = 'owner/repo';
    process.env.GITHUB_RUN_ID = '12345';

    expect(() => getEnvironment()).toThrow('Environment validation failed');
    expect(() => getEnvironment()).toThrow('slackWebhookUrl');
  });

  it('throws when GITHUB_REPOSITORY is missing', () => {
    process.env.GITHUB_TOKEN = 'test-token';
    process.env.SLACK_CI_MONITORING_WEBHOOK_URL = 'https://hooks.example.com/test';
    delete process.env.GITHUB_REPOSITORY;
    process.env.GITHUB_RUN_ID = '12345';

    expect(() => getEnvironment()).toThrow('Environment validation failed');
    expect(() => getEnvironment()).toThrow('repository');
  });

  it('throws when GITHUB_RUN_ID is missing', () => {
    process.env.GITHUB_TOKEN = 'test-token';
    process.env.SLACK_CI_MONITORING_WEBHOOK_URL = 'https://hooks.example.com/test';
    process.env.GITHUB_REPOSITORY = 'owner/repo';
    delete process.env.GITHUB_RUN_ID;

    expect(() => getEnvironment()).toThrow('Environment validation failed');
    expect(() => getEnvironment()).toThrow('runId');
  });

  it('allows missing GITHUB_HEAD_REF for queue health poll workflow', () => {
    process.env.GITHUB_TOKEN = 'test-token';
    process.env.SLACK_CI_MONITORING_WEBHOOK_URL = 'https://hooks.example.com/test';
    process.env.GITHUB_REPOSITORY = 'owner/repo';
    process.env.GITHUB_RUN_ID = '12345';
    delete process.env.GITHUB_HEAD_REF;

    const env = getEnvironment();

    expect(env.headRef).toBeUndefined();
  });
});
