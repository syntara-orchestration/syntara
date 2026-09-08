# Fix Function Parameter Count Warnings and Set the Rule to Error

## Summary

The project has an ESLint rule that limits how many separate parameters a function can take. The rule name is `max-params`. The rule allows 3 parameters today. The rule level is `warn`. This ticket changes every flagged function to use one object parameter. After the fix, change the rule to `error`.

## Background

Code reviewers asked contributors more than once to use one object parameter instead of many separate parameters. This is easier to read at the call site. Each value gets a name. The order of values does not matter.

The team lowered `max-params` from a limit of 5 to a limit of 3. The team set the rule to `warn`, not `error`, so the build does not break today. There are 172 warnings across 120 files right now.

## Goal

1. Change every function flagged by `max-params` to take one object parameter instead of 4 or 5 separate parameters.
2. Change `max-params` from `['warn', 3]` to `['error', 3]` in `frontend/packages/syntara-ui/eslint.config.js`.

## The pattern to follow

See `.claude/skills/frontend-coding-standards/SKILL.md`, section 43, "Use an Object Parameter for 3 or More Arguments."

Change this:

```ts
function createWorkflowActivity(name: string, nodeId: string, status: ExecutionStatus, timestamp: string) {
  /* ... */
}
```

To this:

```ts
function createWorkflowActivity(input: { name: string; nodeId: string; status: ExecutionStatus; timestamp: string }) {
  /* ... */
}
```

Update every place that calls the function. Pass one object, not separate arguments.

**Do not change what a function does.** Only change how the caller passes values in.

## How to get the exact, current list

The counts below are a snapshot. The code may change before work starts on this ticket. Run this command from `frontend/packages/syntara-ui` to get the exact file names, line numbers, and parameter counts at the time you start:

```bash
npx eslint . -f json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for entry in data:
    hits = [m for m in entry['messages'] if m.get('ruleId') == 'max-params']
    if hits:
        print(entry['filePath'])
        for m in hits:
            print(' ', m['line'], m['message'])
"
```

## Suggested work split

172 warnings is too much for one pull request. Split the work into smaller batches. Make one pull request per batch. Suggested batches, by folder:

| Batch | Folder(s) | Warning count (snapshot) |
|---|---|---|
| 1 | `e2e/` | 18 |
| 2 | `src/routes/builder/hooks/` | 24 |
| 3 | `src/routes/builder/utils/` | 17 |
| 4 | `src/routes/builder/node-forms/`, `node-details/`, `edges/`, `panels/`, `registry/`, and other `src/routes/builder/` files | 37 |
| 5 | `src/routes/access-management/`, `src/routes/access/`, `src/routes/approvals/` | 26 |
| 6 | `src/stores/` | 14 |
| 7 | `src/routes/configuration/`, `src/routes/executions/`, `src/routes/workflows/` | 19 |
| 8 | `src/utils/` and remaining files not covered above | 17 |

Total: 172. Re-run the command in the section above before you start each batch. The exact count for a batch may have changed since this ticket was written.

## Out of scope

- The barrel file warnings. A separate ticket, `fix-barrel-file-warnings.md`, covers those.
- Do not change function behavior, only how parameters are passed in.
- Do not raise or lower the `max-params` limit of 3. Only change the severity from `warn` to `error`, and only after every warning is fixed.

## Acceptance criteria

- [ ] Every function flagged by `max-params` today takes one object parameter instead of 4 or more separate parameters.
- [ ] Every call site is updated to pass one object.
- [ ] `max-params` is `['error', 3]` in `frontend/packages/syntara-ui/eslint.config.js`.
- [ ] `npm run lint` in `frontend/packages/syntara-ui` shows 0 warnings and 0 errors for this rule.
- [ ] `npm run typecheck` passes.
- [ ] `npm test` passes.
- [ ] `.claude/skills/frontend-coding-standards/SKILL.md` section 43 says the rule is `error`, not `warn`.
- [ ] `frontend/AGENTS.md` item 34 says the rule is `error`, not `warn`.

## How to check your work

Run this command from `frontend/packages/syntara-ui`:

```bash
npx eslint . 2>&1 | grep "max-params"
```

This command must show no output when the ticket is done.
