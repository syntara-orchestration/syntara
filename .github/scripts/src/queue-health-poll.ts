#!/usr/bin/env node
import { GitHubClient } from './lib/github.js';
import { getEnvironment } from './lib/env.js';
import { setOutput } from './lib/actions-output.js';
import { decideAlert, inferPreviousHealthFromJobs } from './lib/health-state.js';
import type { HealthState } from './lib/types.js';

const MERGE_TIMEOUT_MINUTES = 120;

/**
 * Checks if the merge queue is healthy by verifying recent merge activity.
 * Returns unhealthy if the queue has entries but no merges beyond the timeout.
 */
async function assessHealth(github: GitHubClient, branch: string): Promise<HealthState> {
  console.log('Querying merge queue status...');

  const entries = await github.getMergeQueueEntries(branch);
  const queueDepth = entries.length;

  console.log(`Queue depth: ${queueDepth}`);

  // If queue is empty, we're healthy
  if (queueDepth === 0) {
    return {
      health: 'healthy',
      reason: 'queue_empty',
      queueDepth: 0,
    };
  }

  // Check for recent merges
  const now = Date.now();
  const timeoutAgo = new Date(now - MERGE_TIMEOUT_MINUTES * 60 * 1000);
  const recentMerges = await github.getRecentMerges(branch, timeoutAgo);

  console.log(`Recent merges to ${branch}: ${recentMerges.length}`);

  // If queue has entries but no merges within the timeout, unhealthy
  if (recentMerges.length === 0) {
    // Calculate time since last merge
    const allMerges = await github.getRecentMerges(
      branch,
      new Date(now - 7 * 24 * 60 * 60 * 1000) // Last week
    );

    const lastMergeDate = allMerges[0]
      ? new Date(allMerges[0].mergedAt)
      : new Date();
    const minutesSinceMerge = Math.floor(
      (now - lastMergeDate.getTime()) / (60 * 1000)
    );

    return {
      health: 'unhealthy',
      reason: 'stalled',
      queueDepth,
      minutesSinceMerge,
      oldestPr: entries[0]?.pullRequest.number,
    };
  }

  return {
    health: 'healthy',
    reason: 'merging',
    queueDepth,
  };
}

/**
 * Determines the health state from the previous workflow run.
 * Used to detect state transitions and avoid duplicate alerts.
 */
async function getPreviousHealthState(
  github: GitHubClient,
  currentRunId: number
): Promise<'healthy' | 'unhealthy' | 'unknown'> {
  console.log('Getting previous run state...');

  try {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
    const recentRuns = await github.getWorkflowRuns(
      'merge-queue-health-poll.yml',
      oneHourAgo,
      currentRunId
    );

    if (recentRuns.length === 0) {
      console.log('No previous runs found');
      return 'unknown';
    }

    const previousRun = recentRuns[0];
    console.log(`Previous run ID: ${previousRun.id}`);

    const jobs = await github.getWorkflowRunJobs(previousRun.id);
    return inferPreviousHealthFromJobs(jobs);
  } catch (error) {
    console.warn('Could not determine previous state:', error);
    return 'unknown';
  }
}

/**
 * Assesses merge queue health and writes workflow outputs for alert steps.
 * Does not send Slack messages — named workflow steps handle notifications.
 */
async function main() {
  const env = getEnvironment();

  const github = new GitHubClient(env.githubToken, env.repository);

  const defaultBranch = await github.getDefaultBranch();
  console.log(`Monitoring merge queue for branch: ${defaultBranch}`);

  const currentState = await assessHealth(github, defaultBranch);
  console.log(`Current health: ${currentState.health} (${currentState.reason})`);

  const previousHealth = await getPreviousHealthState(github, env.runId);
  console.log(`Previous health: ${previousHealth}`);

  const queueUrl = github.getQueueUrl(defaultBranch);
  const alert = decideAlert(currentState.health, previousHealth);

  setOutput('health', currentState.health);
  setOutput('alert', alert);
  setOutput('queue_url', queueUrl);
  setOutput('timeout_minutes', String(MERGE_TIMEOUT_MINUTES));
  setOutput('queue_depth', String(currentState.queueDepth ?? 0));
  setOutput('minutes_since_merge', String(currentState.minutesSinceMerge ?? 0));

  if (alert === 'unhealthy') {
    console.log('⚠️  Transition to unhealthy detected — workflow will send alert');
  } else if (alert === 'recovery') {
    console.log('✅ Transition to healthy detected — workflow will send recovery');
  } else {
    console.log('No state transition — no alert needed');
  }
}

main().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
