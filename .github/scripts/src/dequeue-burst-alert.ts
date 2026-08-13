#!/usr/bin/env node
import { GitHubClient } from './lib/github.js';
import { SlackNotifier } from './lib/slack.js';
import { getEnvironment } from './lib/env.js';

const DEQUEUE_THRESHOLD = 3;
const TIME_WINDOW_MINUTES = 30;

/**
 * Detects dequeue bursts in the merge queue and sends Slack alerts.
 * Triggers on the 3rd dequeue within a 30-minute window.
 */
async function main() {
  const env = getEnvironment();

  const github = new GitHubClient(env.githubToken, env.repository);
  const slack = new SlackNotifier(env.slackWebhookUrl);

  console.log('Checking for dequeue burst...');

  // Fetch default branch dynamically
  const defaultBranch = await github.getDefaultBranch();
  console.log(`Monitoring dequeues for branch: ${defaultBranch}`);

  // Get workflow runs from the last 30 minutes
  const thirtyMinsAgo = new Date(Date.now() - TIME_WINDOW_MINUTES * 60 * 1000);
  const recentRuns = await github.getWorkflowRuns(
    'merge-queue-dequeue-alert.yml',
    thirtyMinsAgo,
    env.runId
  );

  const completedCount = recentRuns.length;
  console.log(`Found ${completedCount} completed runs in the last ${TIME_WINDOW_MINUTES} minutes`);

  // Alert only on exactly the 3rd dequeue (2 prior runs + current = 3 total)
  if (completedCount === DEQUEUE_THRESHOLD - 1) {
    console.log(`⚠️  This is the ${DEQUEUE_THRESHOLD}rd dequeue - sending alert`);

    // Extract PR number from merge group ref
    const prNumber = env.headRef?.match(/pr-(\d+)/)?.[1] ?? 'unknown';
    const prUrl = github.getPrUrl(parseInt(prNumber, 10));
    const queueUrl = github.getQueueUrl(defaultBranch);

    await slack.sendDequeueBurstAlert(
      DEQUEUE_THRESHOLD,
      prNumber,
      prUrl,
      queueUrl
    );

    console.log('✅ Alert sent to Slack');
  } else {
    console.log(`No alert needed (${completedCount} prior runs, threshold is ${DEQUEUE_THRESHOLD - 1})`);
  }
}

main().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
