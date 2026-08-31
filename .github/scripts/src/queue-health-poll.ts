#!/usr/bin/env node
import { GitHubClient } from './lib/github.js';
import { SlackNotifier } from './lib/slack.js';
import { getEnvironment } from './lib/env.js';
import type { HealthState } from './lib/types.js';

const MERGE_TIMEOUT_MINUTES = 90;

/**
 * Checks if the merge queue is healthy by verifying recent merge activity.
 * Returns unhealthy if the queue has entries but no merges in 90+ minutes.
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
  const ninetyMinsAgo = new Date(now - MERGE_TIMEOUT_MINUTES * 60 * 1000);
  const recentMerges = await github.getRecentMerges(branch, ninetyMinsAgo);

  console.log(`Recent merges to ${branch}: ${recentMerges.length}`);

  // If queue has entries but no merges in 90 min, unhealthy
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

    // Check which alert step ran in the previous workflow
    const sentUnhealthyAlert = jobs[0]?.steps?.some(
      (step) =>
        step.name === 'Send unhealthy alert' && step.conclusion === 'success'
    );

    const sentRecoveryAlert = jobs[0]?.steps?.some(
      (step) =>
        step.name === 'Send recovery alert' && step.conclusion === 'success'
    );

    if (sentRecoveryAlert) {
      // If recovery was sent, previous state was unhealthy
      return 'unhealthy';
    }

    if (sentUnhealthyAlert) {
      // If unhealthy alert was sent, previous state was healthy (transition to unhealthy)
      return 'healthy';
    }

    // If neither alert was sent, state didn't change - infer from conclusion
    // This is imperfect but works for the steady state
    return 'unknown';
  } catch (error) {
    console.warn('Could not determine previous state:', error);
    return 'unknown';
  }
}

/**
 * Monitors merge queue health and sends alerts on state transitions.
 * Runs every 5 minutes to detect queue backups and recoveries.
 */
async function main() {
  const env = getEnvironment();

  const github = new GitHubClient(env.githubToken, env.repository);
  const slack = new SlackNotifier(env.slackWebhookUrl);

  // Fetch default branch dynamically
  const defaultBranch = await github.getDefaultBranch();
  console.log(`Monitoring merge queue for branch: ${defaultBranch}`);

  // Assess current health
  const currentState = await assessHealth(github, defaultBranch);
  console.log(`Current health: ${currentState.health} (${currentState.reason})`);

  // Get previous health state
  const previousHealth = await getPreviousHealthState(github, env.runId);
  console.log(`Previous health: ${previousHealth}`);

  // Detect transitions and alert
  const queueUrl = github.getQueueUrl(defaultBranch);

  // Transition to unhealthy
  if (
    currentState.health === 'unhealthy' &&
    (previousHealth === 'healthy' || previousHealth === 'unknown')
  ) {
    console.log('⚠️  Transition to unhealthy detected - sending alert');
    await slack.sendQueueBackupAlert(
      currentState.queueDepth!,
      currentState.minutesSinceMerge!,
      queueUrl
    );
    console.log('✅ Unhealthy alert sent to Slack');
    console.log('::set-output name=health::unhealthy');
    return;
  }

  // Transition to healthy
  if (
    currentState.health === 'healthy' &&
    previousHealth === 'unhealthy'
  ) {
    console.log('✅ Transition to healthy detected - sending recovery notification');
    await slack.sendQueueRecoveryAlert(queueUrl);
    console.log('✅ Recovery alert sent to Slack');
    console.log('::set-output name=health::healthy');
    return;
  }

  // No transition
  console.log('No state transition - no alert needed');
  console.log(`::set-output name=health::${currentState.health}`);
}

main().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
