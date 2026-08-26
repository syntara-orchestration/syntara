---
description: "Comprehensive PR review checklist and validation workflow for frontend code."
user-invocable: false
---

# Claude Skill: Pull Request Review & Self-Review

Your goal is to review code with high clarity, consistency, and alignment with the repo's standards. This skill serves two purposes:

1. **Self-review before committing** — Run the quality gates and checklist against your own changes before committing or reporting done.
2. **PR review** — Review a pull request for a teammate or before opening your own.

---

## 1. Identify PR Scope (CRITICAL)

**Before reviewing ANY code, determine the exact changes in the PR:**

### Step 1a: Check the commit history

```bash
# See commits on current branch not in main
git log main..HEAD --oneline
```

### Step 1b: Verify file count matches PR

```bash
# For single-commit PRs, use git show
git show <commit-hash> --stat

# For multi-commit PRs, use git diff with the correct range
git diff <first-commit>^..<last-commit> --stat
```

### Step 1c: Confirm scope with user

**ALWAYS confirm:** "This PR contains X commit(s) changing Y files. Does this match what you expect?"

If the numbers don't match the GitHub PR page (e.g., GitHub shows 3 files but git diff shows 17):

- The branch may be **out of sync with main**
- Use `git show <commit>` for single-commit PRs instead
- Ask the user to clarify which commits to review

### Common Pitfalls to Avoid

| Problem                  | Cause                                                    | Solution                                              |
| ------------------------ | -------------------------------------------------------- | ----------------------------------------------------- |
| Reviewing too many files | `git diff main...HEAD` includes unrelated merged commits | Use `git show <commit>` for the PR's actual commit(s) |
| Missing files            | Wrong commit range                                       | Check `git log` first to identify correct commits     |
| Stale diff               | Branch not rebased                                       | Note this to the user, review only PR commits         |

---

## 2. Load Context

Before reviewing the PR, read:

- `frontend/AGENTS.md` (global instructions)
- Any relevant project guidelines: architecture, naming, lint, testing
- Any domain-specific instructions (e.g., Django, React, PatternFly, SOLID)

---

## 3. Validate Against Guidelines

Check whether the changes follow:

- Existing code patterns
- Repo naming conventions
- Architecture and design principles
- Error-handling standards
- Test strategy
- Security expectations
- Performance constraints
- **Accessibility**: For any UI or test changes, review keyboard use, semantics, labels/roles, focus order, and color/contrast assumptions; confirm new interactive surfaces are reachable and named. Align with `jsx-a11y` / Testing Library rules and axe-style tests where the PR touches user-visible markup.

**Project-Specific:**

- Components in correct location (frontend/packages/syntara-ui/src/components/)
- Uses PatternFly 6 components for UI foundation, styling, and design system
- TanStack Query for server state, Zustand (useWorkflowStore) for workflow state
- No `any` types, uses generated OpenAPI types
- Workflow step types use auto-discovery (`register*.ts` with default export; canvas still uses React Flow nodes)
- No over-engineering (avoid premature abstractions, unnecessary error handling)

### 3a. Recurring Issues Checklist (MANDATORY)

**Run through every item in frontend/AGENTS.md's "Common PR Mistakes -- Quick Checklist".** That checklist is the single source of truth. Items enforced by ESLint at error level are omitted from this table -- ESLint is the source of truth for those. Below are review-specific verification tips for patterns ESLint cannot catch:

| Search for...                                                  | Flags violation of checklist item...                                                                      |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `as` casts on API responses                                    | #1 -- unsafe casts (flag for contract fix, not more casts)                                                |
| New component without `toHaveNoViolations()`                   | #2 -- missing vitest-axe test                                                                             |
| Raw error JSX (`<span>Error`, `<p>Error`, `<div>Error`)        | #3 -- should use `SynErrorState` component                                                                 |
| Manual `useState` per form field                               | #4 -- should use Zod + react-hook-form                                                                    |
| `useForm` with `defaultValues` in modals                       | #5 -- verify `reset()` in `useEffect([isOpen, item])`                                                     |
| Copy-pasted dialogs or action handlers                         | #6 -- extract to shared component/hook                                                                    |
| String literals for type discriminators                        | #9 -- use enum constants from `@syntara/contracts`                                                        |
| Display strings in conditionals                                | #10 -- compare API values, not translatable labels                                                        |
| New route in `AppRoute.tsx` without registry entry             | Add to `e2e/visual-regression/page-registry.ts` (see `frontend/packages/syntara-ui/VISUAL_REGRESSION.md`) |
| Title Case in alert titles                                     | Use sentence case: "Workflow created", not "Created"                                                      |
| Derived data without `useMemo` in custom hooks                 | #12 -- wrap computed maps/arrays in `useMemo`                                                             |
| New `use*.ts` hook without `use*.test.ts(x)`                   | #13 -- every new hook needs a dedicated test file                                                         |
| `useEffect` + `setState` for derived/computed values           | #14 -- compute during render or use `useMemo`                                                             |
| `useEffect` + `setValue` watching form fields                  | #15 -- move cascading resets to field's `onChange` handler                                                |
| `PlusCircleIcon` or non-`RhUi*` icons                          | #17 -- use `RhUiAddIcon`, `RhUiDuplicate`, etc.                                                           |
| Inline style objects (`style={{ ... }}`)                       | #18 -- refactor to CSS module classes                                                                     |
| `let` counter inside `.map()`                                  | #19 -- pre-compute indices immutably                                                                      |
| `aria-label` on `<div>` (non-interactive)                      | span is ESLint; still flag `aria-label` on generic `<div>` (coding standards §27)                         |
| Any `eslint-disable` or `eslint-disable-next-line`             | #20 -- never suppress rules; fix the code so it passes                                                    |
| Hook called unconditionally but used conditionally             | #21 -- extract to a conditionally-rendered wrapper component                                              |
| `useEffect` + `useState` for API calls                         | #22 -- use TanStack Query (`useQuery`/`useMutation`/`useQueries`)                                         |
| Manual `Promise.all` + cancellation for parallel fetches       | #22 -- use `useQueries` from TanStack Query                                                               |
| `// TODO` / `// FIXME` / `// HACK` / `// XXX`                  | #23 -- track deferred work in an issue, not code comments                                                 |
| `SynPageHeader` without `docLink` prop                          | #27 -- hardcoded URLs are ESLint; still pass `docLink={useDocLink('key')}`                                |
| Hardcoded colors in CSS modules                                | ESLint can't catch these; review CSS module files manually                                                |
| `new Date()` in `syntara-mock-api/src/resources/` or `utils/`  | #28 -- use `mockDate.*` from `mockDates.ts` for deterministic visual regression                           |
| `Button` with `onClick={() => navigate(...)}`                  | §34 -- use `<Link>` for navigation, `<Button>` for actions                                                |
| Same `aria-label` on repeated checkboxes/buttons               | §35 -- each instance needs a unique label (e.g., row index or resource name)                              |
| Raw text for invalid ID or not-found states                    | §36 -- use `SynEmptyState` or `Nx*` empty state components                                                 |
| New page test without `expectPageTitle(...)` assertion         | testing guidelines -- add at least one `expectPageTitle` call per page component                          |
| Empty-state CTA without permission check                       | UX §15 -- gate `addData` with permission flag (pass `undefined` if denied)                                |
| New `forwardRef(` usage                                        | #30 -- accept `ref` as a prop (React 19); do not add `forwardRef`                                         |
| New `useRef` + `useEffect` only to attach/detach DOM listeners | #31 -- prefer ref callback cleanup functions (coding standards §38)                                       |
| New `useContext(` usage                                        | #32 -- use `use(Context)` instead (React 19); see coding standards §39                                    |
| Hand-rolled pending mirror state for simple toggle mutations   | #33 -- prefer `useOptimistic` + Action/`mutateAsync` (coding standards §40)                               |

### 3b. Rule Bypass Checks (BLOCKING -- do not approve if any are found)

AI agents and contributors sometimes bypass rules instead of fixing the underlying issue. The following patterns are **merge blockers** -- request changes immediately if any appear in the diff.

**How to scan:** Run these searches against the PR diff. Any match in new or modified lines (not pre-existing context) must be resolved before approval.

```bash
# Run against the PR diff to find bypass attempts
git diff main...HEAD -- '*.ts' '*.tsx' | grep '^+' | grep -v '^+++' | grep -iE 'eslint-disable|@ts-ignore|@ts-expect-error|TODO|FIXME|HACK|XXX|enabled:\s*false'
```

| Pattern in diff                                               | Why it blocks                                                                                          | What to do instead                                                                                                                    |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| `eslint-disable` / `eslint-disable-next-line`                 | Suppresses a rule instead of fixing the code. The rule catches a real problem.                         | Fix the code so the rule passes. If genuinely unfixable, the reviewer (not the author) decides whether a suppression is warranted.    |
| `@ts-ignore` / `@ts-expect-error`                             | Suppresses a TypeScript error instead of fixing the type. Hides real bugs.                             | Fix the type, add a type guard, or update the contract.                                                                               |
| `// TODO` / `// FIXME` / `// HACK` / `// XXX`                 | Deferred work buried in source. Invisible to sprint planning and never addressed.                      | Create an issue and reference it inline: `// Workaround until #12345 adds the endpoint`.                                              |
| `rules: { 'rule-name': { enabled: false } }` in axe config    | Disables an accessibility rule to make a test pass instead of fixing the a11y bug.                     | Fix the component so it passes the axe rule. Only disable with a linked upstream PatternFly issue proving a false positive.           |
| `useEffect` + `useState` for data that TanStack Query handles | Re-implements caching, dedup, retry, and error handling that `useQuery`/`useMutation` already provide. | Use the library API. See .claude/skills/frontend-coding-standards/SKILL.md "Prefer Library and Native Browser APIs Over Custom Code". |
| Custom deep copy, URL parsing, UUID generation                | Re-implements what `structuredClone`, `URLSearchParams`, `generateUUID` already provide.               | Use the native API or existing project utility.                                                                                       |

**Pre-existing suppressions:** If a suppression appears in the diff context but was not added by the PR (no `+` prefix), ignore it. Only flag new additions.

**Also check these review-specific items:**

| Check                                           | How to verify                                                                                                                                                      |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **UI PRs include screenshots**                  | PRs changing visible UI must include screenshots or recordings of key states                                                                                       |
| **New API endpoints have mock handlers**        | Check `frontend/packages/syntara-mock-api/src/handlers.ts`; note exception if backend not yet merged                                                               |
| **`useQueryState` object form**                 | Verify `useQueryState(query, { title, onRetry })` -- not bare string form (see .claude/skills/frontend-coding-standards/SKILL.md §2)                               |
| **Error handling consistency**                  | Verify `useQueryState` / `useMutationErrorHandler` -- no ad-hoc try/catch with custom error display                                                                |
| **userEvent regressions**                       | Check if PR replaces existing `userEvent` calls with `fireEvent` -- that is a regression                                                                           |
| **Unreachable dead code in tests**              | Look for nested `it()` blocks inside other `it()` blocks (after `return` statements)                                                                               |
| **Stale JSDoc/comments after renames**          | When components are renamed, check JSDoc references, `describe` block names, and CSS comments                                                                      |
| **Query invalidation completeness**             | After mutations, verify ALL related queries are invalidated (not just the primary entity)                                                                          |
| **Zero new ESLint warnings**                    | New code must not introduce warnings, even for rules currently set to `warn` -- they will become `error`                                                           |
| **New routes have `requiredPermissions`**       | Every route with access requirements must set `requiredPermissions` in `navigationItems.tsx`; create/edit routes need `routePermission` for `ProtectedRoute` guard |
| **New write actions use `DisabledWithTooltip`** | Create/edit/delete buttons must be wrapped with `DisabledWithTooltip` + domain permission hook; use `permissionTooltip()` for copy                                 |
| **New resources have mock `can_i` handlers**    | `frontend/packages/syntara-mock-api/src/handlers.ts` must include role-aware responses for all 4 roles (admin, viewer, auditor, user)                              |
| **Permission hooks include `isError`**          | Any `useCanI` mock must include `isError: false`; real hook returns `{ allowed, isChecking, isError }`                                                             |
| **Permission cache invalidation**               | After role/assignment mutations, verify `queryClient.invalidateQueries({ queryKey: ['authz', 'can_i'] })` is called                                                |
| **New shared components have stories**          | Components in `frontend/packages/syntara-ui/src/components/` (especially `Nx*`) should have Storybook stories for documentation                                    |
| **Unrelated snapshot changes explained**        | If visual regression screenshots changed for pages not related to the PR, ask why                                                                                  |
| **Visual regression uses stable data**          | Screenshot baselines must use deterministic mock data -- no timestamps, random IDs, or flaky API state                                                             |
| **Gated content hidden during loading**         | Permission-dependent UI (tabs, buttons) should hide until permission check resolves, not flash then disappear                                                      |

### HTML -> PF6 Component Mapping

**Use the PatternFly MCP** (`searchPatternFlyDocs` / `usePatternFlyDocs`) to find the correct PF6 equivalent for any native HTML element. The MCP returns up-to-date documentation, props, and usage examples.

Quick reference for the most common replacements:

| Native HTML       | PF6 Replacement                                                       |
| ----------------- | --------------------------------------------------------------------- |
| `<button>`        | `Button` (`variant="plain"` for icon-only with `icon` prop)           |
| `<p>` / `<small>` | `Content component={ContentVariants.p}` / `ContentVariants.small`     |
| `<ul>` / `<li>`   | `List` / `ListItem`                                                   |
| `<h1>`-`<h6>`     | `Title headingLevel="h1"` or `Content component={ContentVariants.h1}` |

**Keep as native HTML** (no PF equivalent): `<span>`, `<code>`, `<div>` (layout containers), `<strong>`, `<em>`.

For anything not listed above, query the PatternFly MCP before using raw HTML.

---

## 4. Detect Re-invented Patterns

Ask:

- "Does this PR introduce a new pattern that already exists in the codebase?"
- "Is there duplication that should be replaced by existing helpers/modules?"
- "Is this logic available natively in a browser/Web API instead of custom code?"

Examples:

- Use typed API clients (`workflowClient`, `credentialsClient`, `authClient`) instead of raw `fetch()`
- Use `SynErrorState` component instead of custom error markup
- Use `useQueryState` with `onRetry` instead of manual loading/error state management
- Use `useFormMutationErrorHandler` instead of manual 422 error parsing
- Use `getErrorMessage()` / `isConflictError()` from `apiErrors.ts` instead of manual error field checks
- Use `detachPromise(...)` instead of unary `void` for intentionally unawaited promises
- Use PF6 components (`Button`, `List`, `Content`, `Title`) instead of native HTML (`<button>`, `<ul>`, `<p>`, `<h1>`)
- Use `useCursorPagination` instead of manual cursor/filter/queryParams boilerplate
- Use `NxConfirmationDialog` instead of inline Modal+ModalHeader+ModalBody+ModalFooter
- Use `useDialogState` instead of manual `useState` pairs for dialog open/close
- Use `useMemo` for derived data (maps, sorted arrays) in custom hooks instead of recomputing on every render
- Use PF `Content` / `HelperText` / `Title` instead of raw `<span>` / `<p>` / `<div>` for text content
- Use TanStack Query `useQuery`/`useQueries` instead of manual `useEffect` + `useState` for API calls (loses caching, dedup, retry, DevTools)
- Use TanStack Query `useMutation` instead of manual `useEffect` + `Promise` chains for mutations
- Use URLSearchParams instead of manual query parsing
- Use structuredClone instead of manual deep copy
- Use AbortController instead of custom cancellation logic

---

## 5. Recommend Simpler / Native Alternatives

If the PR implements a complex custom solution, propose:

- A native API
- A built-in method
- A standard library replacement
- A repo-wide helper function

---

## 6. Evaluate Test Coverage

Check whether:

- The PR includes tests for critical logic
- Tests follow existing patterns
- Edge cases are covered
- The behavior is stable across browsers/devices
- The test names clearly describe intent
- E2E tests validate the full flow when needed

Generate a list of missing tests and suggested improvements.

---

## 7. Explain the Changes Back (for Documentation)

Generate a markdown summary file that explains:

- What the PR does
- Why the changes matter
- Visual diagrams when relevant
- Before/After examples
- Known tradeoffs
- Any follow-up tasks recommended

---

## 8. Validation Commands

Run these project commands:

```bash
npm run check                         # Static analysis (tsc, lint, format, knip)
npm test                              # All tests
```

Then ask the user to confirm manually:

- UI works in the browser
- Forms, navigation, and modals behave as expected
- No console errors appear
- **Accessibility**: Critical flows usable with keyboard; no obvious missing labels or confusing focus; consider a quick screen-reader or axe pass on changed screens when feasible

---

## 9. Self-Review Quality Gates (Before Committing)

When reviewing your own implementation before committing, verify these gates pass.

**Also run the full checklist in [Section 3a](#3a-recurring-issues-checklist-mandatory)** — the items below complement, not replace, that checklist.

### Implementation Standards

- **React 19**: Functional components with proper hook patterns; `ref` as a prop (no new `forwardRef`); prefer ref callback cleanup functions over `useRef` + `useEffect` for DOM listener lifecycle; prefer `use(Context)` over `useContext`; prefer `useOptimistic` for clear toggle/counter mutations; component composition over prop drilling; controlled components for forms using react-hook-form; Single Responsibility Principle. See [ref as a prop](https://react.dev/blog/2024/12/05/react-19#ref-as-a-prop), [cleanup functions for refs](https://react.dev/blog/2024/12/05/react-19#cleanup-functions-for-refs), [`use`](https://react.dev/reference/react/use), and [`useOptimistic`](https://react.dev/reference/react/useOptimistic).
- **TypeScript**: No `any` types — use `unknown` and narrow with type guards; leverage type inference; discriminated unions for state machines; `as const` for literal narrowing
- **PatternFly 6**: PF6 components for all UI (no native HTML when a PF component exists); layout components (Stack, Flex, Grid) for spacing; design tokens only — no hardcoded values
- **Vitest**: AAA pattern; test user behavior not implementation; Testing Library query priority (`getByRole` > `getByLabelText` > `getByText`); `userEvent.setup()` always; `vitest-axe` for every new component

### Implementation Workflow Check

1. **Checked for reusability** — searched `frontend/packages/syntara-ui/src/components/` and PatternFly docs before creating new components
2. **Implemented incrementally** — happy path first, then edge cases
3. **Wrote tests concurrently** — tests alongside implementation, not after
4. **Verified accessibility** — keyboard navigation, ARIA attributes, axe tests
5. **Library docs consulted** — fetched `llms.txt` URLs from `.claude/skills/frontend-library-references/SKILL.md` for any library used

### Quality Gates (All Must Pass)

1. `npm run check` passes (tsc, lint, format, knip)
2. All tests pass (`npm test`), new tests written for new features
3. WCAG 2.1 AA accessibility standards met
4. UI verified in browser for all states (loaded, empty, error, success)
5. Zero `eslint-disable`, `@ts-ignore`, `@ts-expect-error`, or `// TODO` in new code
6. Zero disabled axe rules in test files
7. No re-implemented library functionality (TanStack Query, react-hook-form, Zod, PatternFly)
8. New routes have `requiredPermissions` / `routePermission` set; new CRUD actions use `DisabledWithTooltip`

### Independent Review (High-Risk Changes)

For high-risk UI changes (new pages, auth flows, complex state management), run `/frontend-review-pr` from a **fresh chat session** before merging. A fresh context provides a second-pass perspective that catches issues the implementation context may overlook.

---

## 10. Final Deliverables

Output should include:

1. A structured PR review
2. A list of issues to fix
3. Recommendations for simplification
4. Test coverage guidance
5. A proposed `.md` explanation file for the PR
