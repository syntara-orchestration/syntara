# GitHub Actions Scripts

TypeScript GitHub Actions scripts for visual-regression review notifications and PR convention checks.

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

Set environment variables and run the visual-regression notification:

```bash
export SLACK_VISUAL_REGRESSION_WEBHOOK_URL="https://hooks.slack.com/services/..."
export VISUAL_REGRESSION_PR_URL="https://github.com/owner/repo/pull/123"
npm run notify:visual-regression-pr
```

PR convention checks (no token needed):

```bash
PR_TITLE="fix(auth): handle expired tokens" npm run check:pr-title
PR_BODY="$(gh pr view 123 --json body -q .body)" npm run check:pr-description
DIFF_BASE=origin/devel npm run check:jira-references   # defaults to HEAD^1..HEAD
```
