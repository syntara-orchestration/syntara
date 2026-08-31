# GitHub Actions Scripts

TypeScript monitoring scripts for the merge queue. Alerts are sent to Slack when the queue stalls or PRs are repeatedly dequeued.

## Development

### Install Dependencies

```bash
npm install
```

### Type Check

```bash
npm run tsc
```

### Run Locally

Set environment variables and run the scripts:

```bash
export GITHUB_TOKEN="ghp_..."
export SLACK_CI_MONITORING_WEBHOOK_URL="https://hooks.slack.com/services/..."
export GITHUB_REPOSITORY="syntara-orchestration/syntara"
export GITHUB_RUN_ID="123456"
export GITHUB_HEAD_REF="gh-readonly-queue/devel/pr-123-abc123"

npm run check-dequeue-burst
npm run check-queue-health
```

## Testing in CI

**Dequeue burst alert:**
- Runs when PRs are dequeued from the merge queue
- To test: lower the threshold to 1 in `dequeue-burst-alert.ts`, then wait for a dequeue event

**Queue health poll:**
- Runs on a scheduled interval
- To test manually: Go to Actions → "Merge Queue Health Poll" → Run workflow

## How It Works

**Dequeue Burst Alert:**
1. Counts how many PRs were dequeued within a recent time window
2. Sends Slack alert when the threshold is exceeded
3. Stops alerting after the window expires

**Queue Health Poll:**
1. Fetches the repository's default branch
2. Checks the merge queue for waiting PRs
3. If empty, the queue is healthy
4. If PRs are waiting, checks for recent merge activity to the default branch
5. Sends alert when the queue becomes unhealthy (PRs waiting + no recent merges)
6. Sends recovery notification when the queue becomes healthy again
