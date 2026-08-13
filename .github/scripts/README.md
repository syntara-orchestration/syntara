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

These scripts are part of the frontend workspace. Running `npm run check` from `/frontend` will type-check them.

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
- To test: lower the threshold to 1 in `dequeue-burst-alert.ts:6`, then wait for a dequeue event

**Queue health poll:**
- Runs every 5 minutes
- To test manually: Go to Actions → "Merge Queue Health Poll" → Run workflow

## How It Works

**Dequeue Burst Alert:**
1. Counts how many PRs were dequeued in the last 30 minutes
2. Sends Slack alert on the 3rd dequeue within that window
3. Stops alerting after 30 minutes

**Queue Health Poll:**
1. Checks the merge queue for waiting PRs
2. If empty, the queue is healthy
3. If PRs are waiting, checks if anything merged to `devel` in the last 60 minutes
4. Sends alert when the queue becomes unhealthy (PRs waiting + no merges)
5. Sends recovery notification when the queue becomes healthy again

## Dependencies

- `@octokit/rest` — GitHub REST API client
- `@octokit/graphql` — GitHub GraphQL API client
- `zod` — Runtime type validation
- `tsx` — TypeScript execution (dev only)
