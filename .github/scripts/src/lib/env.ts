import {
  EnvironmentSchema,
  UnhealthyAlertEnvironmentSchema,
  type Environment,
  type UnhealthyAlertEnvironment,
} from './types.js'

function formatValidationErrors(errors: { path: PropertyKey[]; message: string }[]): string {
  return errors.map((err) => `${err.path.join('.')}: ${err.message}`).join(', ')
}

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
    eventName: process.env.GITHUB_EVENT_NAME,
  }

  // Validate using Zod schema with descriptive error messages
  const result = EnvironmentSchema.safeParse(rawEnv)

  if (!result.success) {
    throw new Error(`Environment validation failed: ${formatValidationErrors(result.error.errors)}`)
  }

  return result.data
}

/** Loads the shared environment plus values passed to the unhealthy alert step. */
export function getUnhealthyAlertEnvironment(): Environment & UnhealthyAlertEnvironment {
  const environment = getEnvironment()
  const result = UnhealthyAlertEnvironmentSchema.safeParse({
    queueDepth: process.env.QUEUE_DEPTH,
    minutesSinceMerge: process.env.MINUTES_SINCE_MERGE,
    timeoutMinutes: process.env.TIMEOUT_MINUTES,
    queueUrl: process.env.QUEUE_URL,
  })

  if (!result.success) {
    throw new Error(`Environment validation failed: ${formatValidationErrors(result.error.errors)}`)
  }

  return { ...environment, ...result.data }
}
