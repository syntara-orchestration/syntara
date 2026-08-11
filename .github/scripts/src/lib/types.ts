import { z } from 'zod';

export const WorkflowRunSchema = z.object({
  id: z.number(),
  name: z.string(),
  head_branch: z.string(),
  status: z.string(),
  conclusion: z.string().nullable(),
  created_at: z.string(),
});

export const MergeQueueEntrySchema = z.object({
  position: z.number(),
  state: z.string(),
  enqueuedAt: z.string(),
  pullRequest: z.object({
    number: z.number(),
    title: z.string(),
  }),
});

export const MergeQueueResponseSchema = z.object({
  repository: z.object({
    mergeQueue: z.object({
      entries: z.object({
        nodes: z.array(MergeQueueEntrySchema),
      }),
    }).nullable(),
  }),
});

export const CommitSchema = z.object({
  commit: z.object({
    committer: z.object({
      date: z.string(),
    }),
  }),
});

export type WorkflowRun = z.infer<typeof WorkflowRunSchema>;
export type MergeQueueEntry = z.infer<typeof MergeQueueEntrySchema>;
export type Commit = z.infer<typeof CommitSchema>;

export type HealthState = {
  health: 'healthy' | 'unhealthy';
  reason: 'queue_empty' | 'merging' | 'stalled';
  queueDepth?: number;
  minutesSinceMerge?: number;
  oldestPr?: number;
};

export type Environment = {
  githubToken: string;
  slackWebhookUrl: string;
  repository: string;
  runId: number;
  headRef?: string;
};
