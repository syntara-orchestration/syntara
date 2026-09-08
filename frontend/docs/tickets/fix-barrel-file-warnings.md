# Fix Barrel File Warnings and Set the Rule to Error

## Summary

The project has a new ESLint rule. The rule finds barrel files. A barrel file is a file that only re-exports code from other files. The rule name is `barrel-files/avoid-barrel-files`. The rule is set to `warn` today. This ticket fixes the real barrel files. After the fix, change the rule to `error`.

## Background

A code reviewer found a new barrel file in a recent pull request. The team decided to stop new barrel files across the whole frontend code, not only in that one file. The team added the rule `barrel-files/avoid-barrel-files` at the `warn` level. A `warn` does not fail the build. This gave the team time to fix old files first.

The rule also flagged 3 files that are not real barrel files. These 3 files hold a large amount of their own code. The rule has a known limit. It does not count an exported function or an exported constant as real code. It only counts code that has no `export` keyword. This makes the rule miscount files that export most of their own content directly.

The team already turned the rule off for these 3 files, in `frontend/packages/syntara-ui/eslint.config.js`:

- `src/stores/useWorkflowStore.ts`
- `src/stores/workflowFactories.ts`
- `src/utils/expressions/defaults.ts`

**Do not touch these 3 files in this ticket. They are out of scope.**

## Goal

1. Remove all 7 real barrel files listed below, or replace them with direct imports.
2. Change `barrel-files/avoid-barrel-files` from `'warn'` to `'error'` in `frontend/packages/syntara-ui/eslint.config.js`.

## Files to fix

| File | Re-exported items | Notes |
|---|---|---|
| `src/components/filters/index.ts` | 7 components + types | Plain barrel. Safe to remove. |
| `src/providers/alerts/index.ts` | `useAlerts`, `AlertProvider`, 4 types | Plain barrel. Safe to remove. |
| `src/providers/brand/index.ts` | `BrandProvider`, `useBrand`, 2 types | Plain barrel. Safe to remove. |
| `src/routes/builder/node-details/index.ts` | 8 node detail components | Plain barrel. Safe to remove. |
| `src/routes/builder/utils/executionState/index.ts` | `ExecutionStateEnricher`, helpers, 5 types | Plain barrel. Safe to remove. |
| `src/routes/builder/utils/validation/index.ts` | `validateWorkflow`, 5 types | Plain barrel. Safe to remove. |
| `src/lib/websocket/index.ts` | `useWebSocket`, 8 types | **Read the special case note below before you touch this file.** |

## Steps for each file

1. Search the codebase for every import that points at the barrel file's folder (for example, `from '../components/filters'`, not `from '../components/filters/TextFilter'`).
2. Change each import to point at the real file that defines the value.
3. Delete the barrel file (`index.ts`).
4. Run the type checker. Fix any import the type checker flags.
5. Run the test suite. Fix any test the change breaks.

### Special case: `src/lib/websocket/index.ts`

This file's top comment calls it "Primary API" for the WebSocket code. This may be an intentional public entry point, not an accidental barrel file. Do this instead of a plain delete:

1. Ask the code owner of the WebSocket module if this file is an intentional public boundary.
2. If the answer is no, follow the normal steps above and delete it.
3. If the answer is yes, keep the file. Add it to the ignore list in `frontend/packages/syntara-ui/eslint.config.js` next to the 3 files already listed there. Write a comment that explains why it stays. Do not silently leave it as an unexplained warning.

## Out of scope

- The 3 files already excluded from the rule (listed above under Background).
- The `max-params` warnings. A separate ticket, `fix-max-params-warnings.md`, covers those.
- Any change to what a component or function does. This ticket only changes where imports point to.

## Acceptance criteria

- [ ] Every file in the "Files to fix" table above is deleted and replaced with direct imports, or is kept with a written reason in `eslint.config.js`.
- [ ] `barrel-files/avoid-barrel-files` is `'error'` in `frontend/packages/syntara-ui/eslint.config.js`.
- [ ] `npm run lint` in `frontend/packages/syntara-ui` shows 0 warnings and 0 errors for this rule.
- [ ] `npm run typecheck` passes.
- [ ] `npm test` passes.
- [ ] `.claude/skills/frontend-coding-standards/SKILL.md` section 44 says the rule is `error`, not `warn`.
- [ ] `frontend/AGENTS.md` item 35 says the rule is `error`, not `warn`.

## How to check your work

Run this command from `frontend/packages/syntara-ui`:

```bash
npx eslint . 2>&1 | grep "barrel-files/avoid-barrel-files"
```

This command must show no output when the ticket is done.
