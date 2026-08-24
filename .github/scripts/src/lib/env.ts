import { EnvironmentSchema, type Environment } from './types.js';

/**
 * Loads and validates GitHub Actions environment variables.
 * Throws descriptive errors if required variables are missing or invalid.
 */
export function getEnvironment(): Environment {
  const rawEnv = {
    githubToken: process.env.GITHUB_TOKEN,
    slackWebhookUrl: process.env.SLACK_CI_MONITORING_WEBHOOK_URL,
    repository: process.env.GITHUB_REPOSITORY,
    runId: process.env.GITHUB_RUN_ID ? parseInt(process.env.GITHUB_RUN_ID, 10) : undefined,
    headRef: process.env.GITHUB_HEAD_REF,
  };

  // Validate using Zod schema with descriptive error messages
  const result = EnvironmentSchema.safeParse(rawEnv);

  if (!result.success) {
    const errors = result.error.errors.map(err => `${err.path.join('.')}: ${err.message}`).join(', ');
    throw new Error(`Environment validation failed: ${errors}`);
  }

  return result.data;
}
