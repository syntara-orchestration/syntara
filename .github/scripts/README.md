# GitHub Actions Scripts

TypeScript utilities for GitHub Actions workflows.

## Structure

```
.github/scripts/
├── src/
│   ├── dequeue-burst-alert.ts    # Detection 1: Burst dequeue detector
│   ├── queue-health-poll.ts      # Detection 2: Queue backup detector
│   └── lib/
│       ├── github.ts             # GitHub API client wrapper
│       ├── slack.ts              # Slack Block Kit message builders
│       ├── types.ts              # Shared type definitions
│       └── env.ts                # Environment variable validation
├── package.json
├── tsconfig.json
└── README.md
```

## Development

### Install Dependencies

```bash
npm install
```

### Type Check

```bash
npm run tsc
```

This package is also included in the frontend workspace, so `npm run check` from `/frontend` will type-check these scripts.

### Run Locally (for testing)

Set required environment variables and run the scripts:

```bash
export GITHUB_TOKEN="ghp_..."
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export GITHUB_REPOSITORY="syntara-orchestration/syntara"
export GITHUB_RUN_ID="123456"
export GITHUB_HEAD_REF="gh-readonly-queue/devel/pr-123-abc123"

npm run check-dequeue-burst
npm run check-queue-health
```

## Testing in CI

Both workflows can be triggered manually via `workflow_dispatch`:

1. **Dequeue burst alert** (`merge-queue-dequeue-alert.yml`):
   - Triggers on `merge_group` events when PRs are dequeued
   - Test by temporarily lowering the threshold to 1 in `dequeue-burst-alert.ts`
   - Or wait for natural dequeue events

2. **Queue health poll** (`merge-queue-health-poll.yml`):
   - Triggers every 5 minutes via cron
   - Manually trigger: Actions → "Merge Queue Health Poll" → Run workflow

## How It Works

### Dequeue Burst Alert

1. Queries GitHub API for workflow runs in the last 30 minutes
2. Counts completed runs (excluding current)
3. If exactly 2 prior runs exist (current = 3rd dequeue), sends Slack alert
4. Self-suppresses after 30-minute window expires

### Queue Health Poll

1. Queries merge queue via GraphQL for current entries
2. If empty, exits early (healthy)
3. If entries exist, checks for merges to `devel` in last 60 minutes
4. Compares current health with previous run to detect state transitions
5. Sends alert on transition to unhealthy
6. Sends recovery notification on transition to healthy

## Dependencies

- `@octokit/rest` - GitHub REST API client
- `@octokit/graphql` - GitHub GraphQL API client
- `zod` - Runtime type validation
- `tsx` - TypeScript execution (dev only)
