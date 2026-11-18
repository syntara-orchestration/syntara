---
name: frontend-review-pr
description: "Review frontend changes against the project's PR checklist and coding standards. Use when reviewing a frontend pull request or branch, when asked to review UI/React/TypeScript changes, and as a self-review before committing frontend code or reporting a frontend task as done."
user-invocable: true
---

# Frontend PR Review

Review frontend changes for correctness, consistency, and alignment with this repo's standards. This skill has two modes:

1. **PR review** — review a teammate's pull request, or your own branch before opening a PR.
2. **Self-review** — check your own changes before committing or reporting a task as done. Run sections 1 and 3–7; skip the write-up in section 8.

ESLint is the source of truth for every rule it enforces at `error` level. Do not re-check those by hand — run `npm run check` and report failures. This checklist covers what ESLint **cannot** catch.

---

## 1. Identify the Scope

Determine exactly which changes are under review before reading any code. The default branch is `devel`.

```bash
# Use the remote that points at the canonical repo. In a fork, `origin` is
# usually the fork and `upstream` is the canonical repo.
REMOTE=$(git remote | grep -qx upstream && echo upstream || echo origin)
git fetch "$REMOTE" devel
BASE=$(git merge-base "$REMOTE/devel" HEAD)

# PR review by number: check the PR out first, so later diffs, greps, and
# `npm run check` run against the PR's code, not your current branch
gh pr checkout <number>
gh pr view <number> --json title,body,files,commits

# Commits and files in scope
git log --oneline "$BASE"..HEAD
git diff --stat "$BASE"   # compares against the working tree, so self-review includes uncommitted changes
```

Shell variables do not persist between separate shell calls; recompute `REMOTE` and `BASE` in each command that uses them.

State the scope at the top of your review (e.g. "3 commits, 12 files"). If it does not match what the user or the GitHub PR page describes — usually because the branch is stale or includes merged commits — say so and review only the PR's own commits (`git show <sha>`). Ask the user only when you cannot tell which commits belong to the PR.

Read every changed file in full, not just the diff hunks — context matters for spotting duplication and broken patterns.

---

## 2. Load Context

Read the guidance relevant to the files touched:

- `frontend/AGENTS.md` — project-wide agent instructions
- `.agents/skills/frontend-coding-standards/SKILL.md` — component, hook, API, form, and permission patterns
- `.agents/skills/frontend-patternfly-ux/SKILL.md` — when the PR changes visible UI
- `.agents/skills/frontend-testing-guidelines/SKILL.md` — when the PR adds or changes unit tests
- `.agents/skills/frontend-playwright-e2e/SKILL.md` — when the PR adds or changes E2E tests

Skip any skill already loaded in this conversation.

---

## 3. Review Checklist

### 3a. Recurring Issues (MANDATORY)

These are the issues most often flagged in real reviews of this repo and not caught by ESLint. Check every one against the diff.

| Search for...                                                                                                                            | Flag and recommend...                                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `as` casts on API responses                                                                                                              | Typed client responses or type guards; fix the contract rather than adding casts                                                          |
| New component without a `toHaveNoViolations()` test                                                                                      | A `vitest-axe` test, including expanded/interactive states                                                                                |
| Raw error JSX (`<span>Error`, `<p>Error`, `<div>Error`)                                                                                  | `SynErrorState` with the raw error object and `onRetry`                                                                                   |
| Manual `useState` per form field                                                                                                         | Zod + react-hook-form with `zodResolver`                                                                                                  |
| `useForm` with `defaultValues` in an edit modal                                                                                          | `reset()` in a `useEffect` keyed on `[isOpen, item]`                                                                                      |
| Copy-pasted dialogs, action handlers, or boolean expressions                                                                             | Shared component, hook, or predicate (`useDialogState`, `useDeleteAction`, `useCursorPagination`)                                         |
| Manual cursor/filter/query-param state on a list page                                                                                    | `useCursorPagination` + `useCursorReset`                                                                                                  |
| String literals for type discriminators                                                                                                  | Enum constants from `@syntara/contracts`                                                                                                  |
| Display strings in conditionals                                                                                                          | Compare API values or enum constants, not translatable labels                                                                             |
| Confirmation prompt not using `SynConfirmationDialog` (lint only flags raw `Modal`s with a static destructive title and a danger button) | `SynConfirmationDialog` with the correct severity tier (coding standards §12)                                                             |
| `getByTestId` in unit tests where an accessible query works                                                                              | `getByRole` > `getByLabelText` > `getByText`; `getByTestId` only as a last resort                                                         |
| Ad-hoc `try`/`catch` with custom error display; manual 422 or field-error parsing                                                        | `useQueryState`, `useMutationErrorHandler` / `useFormMutationErrorHandler`, `getErrorMessage()` / `isConflictError()` from `apiErrors.ts` |
| Raw PF `Label`                                                                                                                           | `SynLabel` for system labels, `SynUserTag` for user-authored tags                                                                         |
| Derived maps/arrays in custom hooks without `useMemo`                                                                                    | Wrap computed values in `useMemo`                                                                                                         |
| New `use*.ts` hook without `use*.test.ts(x)`                                                                                             | A dedicated hook test file                                                                                                                |
| `useEffect` + `setState` for derived values                                                                                              | Compute during render or use `useMemo`                                                                                                    |
| `useEffect` + `setValue` watching form fields                                                                                            | Move cascading resets into the field's `onChange` handler                                                                                 |
| Hook called unconditionally but used conditionally                                                                                       | Extract to a conditionally rendered wrapper component                                                                                     |
| Non-`RhUi*` icons (e.g. `PlusCircleIcon`)                                                                                                | `RhUiAddIcon`, `RhUiDuplicate`, etc.                                                                                                      |
| Inline style objects (`style={{ ... }}`)                                                                                                 | CSS module classes                                                                                                                        |
| Hardcoded colors or spacing in CSS modules                                                                                               | PF semantic design tokens                                                                                                                 |
| `let` counter inside `.map()` / `.forEach()`                                                                                             | Pre-computed indices or the callback's index parameter                                                                                    |
| `aria-label` on a generic `<div>`                                                                                                        | Remove it; `aria-label` belongs on interactive elements, widgets, and landmarks                                                           |
| Same `aria-label` on repeated checkboxes/buttons                                                                                         | A unique label per instance (row index or resource name)                                                                                  |
| `Button` with `onClick={() => navigate(...)}`                                                                                            | `<Link>` for navigation, `<Button>` for actions                                                                                           |
| Raw text for invalid-ID or not-found states                                                                                              | `SynEmptyStateNoData` / other `SynEmptyState*` components                                                                                 |
| Empty-state CTA without a permission check                                                                                               | Gate `addData` with the permission flag (pass `undefined` if denied)                                                                      |
| `SynPageHeader` without `docLink`                                                                                                        | `docLink={useDocLink('key')}`, with the key in `docsUrls.json`                                                                            |
| New page test without `expectPageTitle(...)`                                                                                             | At least one `expectPageTitle` assertion per page component                                                                               |
| New route in `AppRoute.tsx` without a visual-regression entry                                                                            | An entry in `e2e/visual-regression/page-registry.ts` (see `frontend/packages/syntara-ui/VISUAL_REGRESSION.md`)                            |
| Title Case in alert/toast titles                                                                                                         | Sentence case: "Workflow created"                                                                                                         |
| `new Date()` in `syntara-mock-api` seed data outside the linted folders                                                                  | `mockDate.*` from `mockDates.ts` for deterministic visual regression                                                                      |
| New `forwardRef(`                                                                                                                        | Accept `ref` as a prop (React 19)                                                                                                         |
| New `useRef` + `useEffect` only to attach/detach DOM listeners                                                                           | A ref callback that returns a cleanup function                                                                                            |
| New `useContext(`                                                                                                                        | `use(Context)` (React 19)                                                                                                                 |
| Hand-rolled pending mirror state for a simple toggle mutation                                                                            | `useOptimistic` inside a `startTransition` Action with `mutateAsync`                                                                      |
| New `type`/`interface` duplicating an existing imported type                                                                             | `type X = Y` or extend the existing type                                                                                                  |
| `// TODO` / `// FIXME` / `// HACK` / `// XXX`                                                                                            | Do the work now, or file an issue and reference it inline (`// Inline type until #12345 adds the schema`)                                 |

### 3b. Rule Bypasses (BLOCKING)

Rule bypasses are merge blockers — request changes if any appear on lines the PR **adds**. Ignore pre-existing suppressions in diff context.

```bash
REMOTE=$(git remote | grep -qx upstream && echo upstream || echo origin)
git diff "$(git merge-base "$REMOTE/devel" HEAD)" -- '*.ts' '*.tsx' | grep '^+' | grep -v '^+++' \
  | grep -iE 'eslint-disable|@ts-ignore|@ts-expect-error|enabled:\s*false'
```

| Pattern in diff                                                                    | Why it blocks                                                            | What to do instead                                                                                              |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `eslint-disable` / `eslint-disable-next-line`                                      | Suppresses a rule instead of fixing the code                             | Fix the code. If genuinely unfixable, the reviewer (not the author) decides whether a suppression is warranted. |
| `@ts-ignore` / `@ts-expect-error`                                                  | Hides a real type error                                                  | Fix the type, add a type guard, or update the contract                                                          |
| `rules: { 'rule-name': { enabled: false } }` in axe                                | Disables an a11y rule to make a test pass                                | Fix the component; only disable with a linked upstream PatternFly issue proving a false positive                |
| `useEffect` + `useState` (or manual `Promise.all`) for data TanStack Query handles | Re-implements caching, dedup, retry, and error handling                  | `useQuery` / `useMutation` / `useQueries`; `refetchInterval` for polling                                        |
| Custom deep copy, URL parsing, UUID generation                                     | Re-implements `structuredClone`, `URL`/`URLSearchParams`, `generateUUID` | Use the native API or the existing project utility                                                              |

### 3c. Permissions, Mocks, and PR Completeness

| Check                                           | How to verify                                                                                                           |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **New routes are gated**                        | `requiredPermissions` in `navigationItems.tsx`; create/edit routes set `routePermission` for `ProtectedRoute`           |
| **New write actions are gated**                 | Create/edit/delete buttons wrapped in `DisabledWithTooltip` + a domain permission hook; copy from `permissionTooltip()` |
| **Gated UI hidden while loading**               | Permission-dependent tabs/buttons stay hidden until the check resolves, rather than flashing then disappearing          |
| **Permission cache invalidation**               | Role/assignment mutations call `queryClient.invalidateQueries({ queryKey: ['authz', 'can_i'] })`                        |
| **Query invalidation is complete**              | After mutations, all related queries are invalidated, not just the primary entity                                       |
| **New API endpoints have mock handlers**        | `frontend/packages/syntara-mock-api/src/handlers.ts`; note an exception if the backend has not merged yet               |
| **New resources have role-aware `can_i` mocks** | Responses for all 4 roles (admin, viewer, auditor, user); `useCanI` mocks include `isError: false`                      |
| **New shared components have stories**          | `Syn*` components in `frontend/packages/syntara-ui/src/components/` have Storybook stories                              |
| **UI PRs include screenshots**                  | Screenshots or recordings of the key states are in the PR description                                                   |
| **Unrelated snapshot changes explained**        | Visual-regression changes for unrelated pages need an explanation                                                       |
| **Visual regression uses stable data**          | Baselines use deterministic mock data — no timestamps, random IDs, or flaky API state                                   |
| **No new lint warnings**                        | `npm run check` passes with warnings; run `npm run lint` and flag any new warnings on changed lines                     |
| **Docs stay in sync**                           | Behavior changes update the related docs (`frontend/docs/`, READMEs, skills)                                            |
| **Stale names after renames**                   | JSDoc, `describe` names, and CSS comments still match renamed components                                                |

### 3d. General Review

Beyond the checklists, check for:

- **Existing patterns** — does the PR introduce a pattern that already exists in the codebase, or duplicate an existing helper?
- **Simpler alternatives** — could a native browser API, a library feature (TanStack Query `select`/`enabled`/`refetchInterval`, react-hook-form `useFieldArray`, Zod `.transform()`), or a repo helper replace custom code?
- **Over-engineering** — premature abstractions or unnecessary error handling.
- **Types** — no `any`; generated OpenAPI types used.
- **Architecture** — shared components live in `frontend/packages/syntara-ui/src/components/`; TanStack Query for server state, Zustand (`useWorkflowStore`) for workflow state; workflow step types use auto-discovery (`register*.ts` with a default export).
- **Accessibility** — for any user-visible markup: keyboard use, semantics, labels/roles, focus order, and not relying on color alone. New interactive surfaces must be reachable and named.
- **Native HTML vs PatternFly** — use PF6 components when one exists; query the PatternFly MCP (`searchPatternFlyDocs` / `usePatternFlyDocs`) if unsure. Native `<span>`, `<code>`, `<div>` (layout), `<strong>`, `<em>` are fine.

---

## 4. Evaluate Test Coverage

Check that:

- Critical logic is tested, following existing test patterns
- Edge cases are covered (empty, error, filtered-with-no-results states)
- Test names accurately describe what is asserted
- Refactors leave no test exercising the old code path and no previously tested branch untested
- Tests use exact text matches where text is fixed, with repeated label strings extracted to a constant
- No nested `it()` blocks or assertions that can never run
- No regressions from `userEvent` back to `fireEvent`
- E2E tests are self-contained (create and clean up their own data in `try/finally`) when the flow needs one

List any missing tests with a concrete suggestion for each.

---

## 5. Validate

From `frontend/`:

```bash
npm run check   # tsc, lint, format, knip — mirrors the CI "Checks" job
npm test
```

Report any failures with the output. Do not claim the checks pass if you did not run them.

---

## 6. Manual Verification

Ask the user (or, for self-review, do it yourself with a browser MCP) to confirm:

- The UI works in the browser for every state: loaded, empty, error, success
- Forms, navigation, and modals behave as expected
- No console errors appear
- Critical flows are usable with the keyboard, with sensible focus order and no missing labels

---

## 7. Self-Review Gates

When reviewing your own work, all of these must hold before you commit or report done:

1. `npm run check` and `npm test` pass; new features have new tests
2. Sections 3a–3c are clean for the lines you changed
3. No new `eslint-disable`, `@ts-ignore`, `@ts-expect-error`, or disabled axe rules
4. No new ESLint warnings on the lines you changed (`npm run check` does not fail on warnings)
5. UI verified in the browser for all states; WCAG 2.1 AA met

For high-risk changes (new pages, auth flows, complex state management), recommend running this skill again from a **fresh session** before merging — a fresh context catches what the implementing context overlooks.

---

## 8. Deliverables (PR Review Mode)

Report:

1. **Scope** — commits and files reviewed
2. **Summary** — what the PR does, in two or three sentences
3. **Findings**, grouped by severity, each with `file:line` and a concrete fix:
   - **Blocking** — must fix before merge (bugs, section 3b bypasses, missing gating, broken patterns)
   - **Suggestion** — should fix (duplication, simpler alternatives, missing tests)
   - **Nitpick** — optional style points
4. **Test coverage gaps**
5. **Validation results** from section 5

Lead with Blocking findings. If there are none, say so plainly.
