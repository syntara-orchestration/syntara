#!/usr/bin/env node
import { GitHubClient } from './lib/github.js';
import { SlackNotifier } from './lib/slack.js';
import { getEnvironment } from './lib/env.js';

/** Number of merges within the time window that triggers an alert */
const DEQUEUE_THRESHOLD = 3;

/** Time window in minutes for detecting merge bursts */
const TIME_WINDOW_MINUTES = 45;

/**
 * Detects dequeue bursts in the merge queue and sends Slack alerts.
 * Runs on a schedule. Uses recently merged PRs as a proxy for queue activity.
 * Alerts when multiple PRs are merged within a time window (indicating
 * successful dequeues), but only if current queue is non-empty (suggesting
 * more PRs are waiting that might also fail).
 */
async function main() {
  const env = getEnvironment();

  const github = new GitHubClient(env.githubToken, env.repository);
  const slack = new SlackNotifier(env.slackWebhookUrl);

  console.log('Checking for recent merge activity...');

  // Fetch default branch dynamically
  const defaultBranch = await github.getDefaultBranch();
  console.log(`Monitoring merge activity for branch: ${defaultBranch}`);

  // Get current queue state
  const currentEntries = await github.getMergeQueueEntries(defaultBranch);
  const currentPrNumbers = currentEntries.map(e => e.pullRequest.number).sort((a, b) => a - b);
  console.log(`Current queue has ${currentPrNumbers.length} PRs: ${currentPrNumbers.join(', ') || 'none'}`);

  // Get recently merged PRs (successful dequeues)
  const thirtyMinsAgo = new Date(Date.now() - TIME_WINDOW_MINUTES * 60 * 1000);
  const recentMerges = await github.getRecentMerges(defaultBranch, thirtyMinsAgo);

  console.log(`Found ${recentMerges.length} merged PRs in the last ${TIME_WINDOW_MINUTES} minutes`);

  if (recentMerges.length > 0) {
    console.log('Recent merges:');
    recentMerges.forEach(m => console.log(`  - PR #${m.number}: ${m.title} (merged ${m.mergedAt})`));
  }

  // Alert if we see rapid merge activity (potential dequeue burst)
  // This is a simplified heuristic: rapid merges + non-empty queue might indicate
  // that multiple PRs are being processed quickly, which could mean CI instability
  // or other issues affecting the queue.
  if (recentMerges.length < DEQUEUE_THRESHOLD || currentEntries.length === 0) {
    console.log(`No alert needed (${recentMerges.length} merges, ${currentEntries.length} queued, threshold is ${DEQUEUE_THRESHOLD})`);
    return;
  }

  console.log(`⚠️  ${recentMerges.length} merges detected with ${currentEntries.length} PRs still queued - potential dequeue burst`);

  const prNumbers = recentMerges.map(m => `#${m.number}`).join(', ');
  const prUrls = recentMerges.map(m => github.getPrUrl(m.number)).join('\n');
  const queueUrl = github.getQueueUrl(defaultBranch);

  await slack.sendDequeueBurstAlert(
    recentMerges.length,
    prNumbers,
    prUrls,
    queueUrl
  );

  console.log('✅ Alert sent to Slack');
}

main().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
