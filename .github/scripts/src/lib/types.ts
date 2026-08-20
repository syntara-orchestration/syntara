import { z } from 'zod';

/**
 * Validates GitHub Actions workflow run data from the REST API.
 * Contains workflow execution metadata including ID, status, and branch.
 */
export const WorkflowRunSchema = z.object({
  id: z.number(),
  name: z.string(),
  head_branch: z.string(),
  status: z.string(),
  conclusion: z.string().nullable(),
  created_at: z.string(),
});

/**
 * Validates a single entry in the GitHub merge queue from GraphQL API.
 * Represents a PR waiting to merge with its position and metadata.
 */
export const MergeQueueEntrySchema = z.object({
  position: z.number(),
  state: z.string(),
  enqueuedAt: z.string(),
  pullRequest: z.object({
    number: z.number(),
    title: z.string(),
  }),
});

/**
 * Validates the GraphQL response for merge queue queries.
 * Contains nested repository and merge queue data structure.
 */
export const MergeQueueResponseSchema = z.object({
  repository: z.object({
    mergeQueue: z.object({
      entries: z.object({
        nodes: z.array(MergeQueueEntrySchema),
      }),
    }).nullable(),
  }),
});

/**
 * Validates GitHub commit data from the REST API.
 * Used to check when the last commit was merged to a branch.
 */
export const CommitSchema = z.object({
  sha: z.string(),
  commit: z.object({
    message: z.string(),
    committer: z.object({
      name: z.string(),
      date: z.string(),
    }),
  }),
  html_url: z.string(),
});

/**
 * Validates required GitHub Actions environment variables.
 * All secrets and context values needed by the monitoring scripts.
 */
export const EnvironmentSchema = z.object({
  githubToken: z.string().min(1, 'GITHUB_TOKEN is required'),
  slackWebhookUrl: z.string().url('SLACK_CI_MONITORING_WEBHOOK_URL must be a valid URL'),
  repository: z.string().min(1, 'GITHUB_REPOSITORY is required'),
  runId: z.number().int().positive('GITHUB_RUN_ID must be a positive integer'),
  headRef: z.string().optional(),
});

export type WorkflowRun = z.infer<typeof WorkflowRunSchema>;
export type MergeQueueEntry = z.infer<typeof MergeQueueEntrySchema>;
export type Commit = z.infer<typeof CommitSchema>;

/**
 * Represents the current health state of the merge queue.
 * Includes health status, reason, and optional diagnostic data.
 */
export type HealthState = {
  health: 'healthy' | 'unhealthy';
  reason: 'queue_empty' | 'merging' | 'stalled';
  queueDepth?: number;
  minutesSinceMerge?: number;
  oldestPr?: number;
};

export type Environment = z.infer<typeof EnvironmentSchema>;
