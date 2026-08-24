# AI Agent Instructions

This file provides guidance to AI coding assistants when working in the frontend workspace.

## Skills (load on demand)

**Do not load all skills at once** — read each skill file when its trigger condition is met. If a loaded skill tells you to read another skill already loaded in this conversation, skip the re-read.

<!-- NOTE: Executable agent hooks (skill-gate.sh, skill-triggers.json, settings.json)
     were removed for supply-chain safety and are not allowed upstream. Skills are
     advisory — read them on-demand per the triggers below. See
     ../.github/AI_AGENT_POLICY.md. -->

| Trigger                                                                             | Skill file to read                                                                        |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Before implementing, reviewing, or refactoring any frontend code**                | `.claude/skills/frontend-specialist/SKILL.md`                                             |
| **Before writing or modifying any component, page, or UI code**                     | `.claude/skills/frontend-patternfly-ux/SKILL.md`                                          |
| **Before writing or reviewing any test file** (unit, integration, or accessibility) | `.claude/skills/frontend-testing-guidelines/SKILL.md`                                     |
| **Before writing or reviewing any E2E / Playwright test**                           | `.claude/skills/frontend-playwright-e2e/SKILL.md`                                         |
| **Before committing code or reporting a task as done**                              | `.claude/skills/frontend-pr-review/SKILL.md` (self-review against PR checklist)           |
| **Before writing or modifying any component, hook, or pattern**                     | `.claude/skills/frontend-coding-standards/SKILL.md`                                       |
| **Before writing code using React, Zod, Zustand, Vitest, Vite, or TanStack Query**  | `.claude/skills/frontend-library-references/SKILL.md` (fetch the relevant `llms.txt` URL) |

### Storybook MCP (when available)

When the Storybook MCP is available in the session, use its tools for all component and story work — it surfaces live documentation, rendered previews, and story conventions without requiring you to read source files.

**CRITICAL: Never hallucinate component properties.** Before using any prop on a component — including seemingly obvious ones like `shadow`, `size`, `variant` — you must verify it is actually documented. A story name may not reflect the underlying prop name, so always check the documentation, not just story names.

**Workflow:**

1. Call `list-all-documentation` to discover component IDs.
2. Call `get-documentation` for the specific component to see all documented props and examples. Only use props that appear there.
3. If a prop is not documented, **do not assume it exists based on naming conventions or patterns from other libraries** — ask the user instead.
4. Before creating or editing any `.stories.*` file, call `get-storybook-story-instructions` for current conventions.
5. After any component or story change, call `preview-stories` and **always include every returned preview URL in your response**.
6. If `get-documentation` doesn't show the variant you need, call `get-documentation-for-story` for that specific story.
7. **Before implementing any confirmation dialog**, call `get-documentation` with id `"components-dialogs-nxconfirmationdialog"` — the `NxConfirmationDialog` stories are the primary source of truth for tier selection, prop usage, title format, body copy, checkbox labels, and button labels.

### Shell Command Rules

**Never use bare `cd pkg && command`** — shell state does not persist between Bash calls and this pattern fails under `eval`. Use a subshell or `--prefix` instead:

```bash
(cd packages/syntara-ui && npx eslint 'src/**/*.ts')  # subshell
npm --prefix packages/syntara-ui run lint              # npm script
npx --prefix packages/syntara-ui vitest run path/to/test.test.ts
```

### Accessibility review (always)

Treat accessibility as part of every UI change, not an optional follow-up:

- **While implementing**: Prefer semantic HTML and PatternFly patterns; meaningful labels, names, and roles; keyboard operability where there is interactivity; do not rely on color alone for meaning.
- **While reviewing** (code or PR): Check new or changed UI for the above, for `eslint-plugin-jsx-a11y` / Testing Library expectations, and for tests (`vitest-axe` where appropriate). Flag regressions and missing coverage.
- See [`.claude/skills/frontend-testing-guidelines/SKILL.md`](../.claude/skills/frontend-testing-guidelines/SKILL.md) — "Accessibility Testing" for project tooling (ESLint, vitest-axe, E2E axe-core).

### TypeScript and ESLint Guardrails

**CRITICAL: Always follow TypeScript best practices and do not introduce new ESLint warnings.**

- **TypeScript first**: Prefer strict, explicit typing and type-safe patterns. Avoid `any`, avoid unsafe casts unless absolutely necessary, and use existing shared types or contract types whenever possible.
- **Respect existing lint rules**: New or modified code should not add fresh ESLint warnings or errors, even in areas where older warnings still exist.
- **Leave files no worse than you found them**: If you touch a file, avoid increasing its warning count. When practical, reduce nearby warnings as part of the change.
- **Refactor instead of suppressing**: Prefer clearer control flow, smaller functions, extracted helpers, and stronger types over disabling rules.
- **Validate before finishing**: After substantive edits, run the relevant lint/type-check commands for the affected package and fix any issues introduced by the change.
- **Use `detachPromise(...)` for fire-and-forget promises**: Import from `packages/syntara-ui/src/utils/detachPromise.ts`. The unary `void` operator is forbidden by ESLint `no-void`.

### Common PR Mistakes — Quick Checklist

**CRITICAL: Address ALL of these before opening a PR. For detailed examples, see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md).**

Items enforced by ESLint at error level are omitted -- ESLint is the source of truth for those. The items below cover patterns ESLint cannot catch:

1. **No unsafe `as` casts on API responses** -- use typed client responses or type guards
2. **`vitest-axe` test for every new component** -- at least one `toHaveNoViolations()`
3. **`SynErrorState` component** -- never raw error markup; pass raw error object + `onRetry`
4. **Zod + react-hook-form** -- never manual `useState` per field; use `zodResolver`
5. **Reset `defaultValues` in edit modals** -- `reset()` in `useEffect` keyed on `[isOpen, item]`
6. **Extract shared patterns** -- use `NxConfirmationDialog`, `useDialogState`, `useDeleteAction`, `useCursorPagination`
7. **UI PRs must include screenshots** or screen recordings showing key states
8. **New API endpoints need mock handlers** in `packages/syntara-mock-api/src/handlers.ts`
9. **Use enum constants** from `@syntara/contracts` -- never string literals for discriminators
10. **Never compare display strings in logic** -- compare API values or enum constants, not translatable labels
11. **No nested React components (Sonar S6478)** -- do not declare components inside another component; for PatternFly `toggle` / similar props use a **module-scoped** child component and pass data as props (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §18)
12. **`NxLabel` for system labels, `NxUserTag` for user-authored tags** -- use `NxLabel` (filled, compact by default) for all system-generated labels: statuses, categories, metadata badges, counts, and filter chips. Use `NxUserTag` (outline, compact by default) only for user-authored content such as workflow tags or user-entered values. Never use PF `Label` directly.
13. **`useMemo` for derived data in hooks** -- wrap computed maps/arrays/filtered lists from query results in `useMemo` to avoid new references on every render (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §21)
14. **New hooks need test files** -- every new `use*.ts` hook must have a dedicated `use*.test.ts(x)` with coverage, not just indirect coverage from a component test
15. **No unnecessary `useEffect`** -- never use `useEffect` to compute derived state, chain state updates, or handle user events; use event handlers, `useMemo`, or inline calculations instead ([React docs](https://react.dev/learn/you-might-not-need-an-effect), [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §23)
16. **Cascading form field resets belong in `onChange`** -- when one field change should reset another, put the `setValue()` calls in the field's `onChange` handler, not in a `useEffect` watching the field value
17. **E2E tests must be self-contained** -- every E2E test must create ALL resources it needs and delete ALL created resources in a `try-finally` block; `test.skip()` is only acceptable for data that is impossible to create programmatically (e.g., human-approved records, external integrations) — if the test can create the data via API, it must (see [`.claude/skills/frontend-playwright-e2e/SKILL.md`](../.claude/skills/frontend-playwright-e2e/SKILL.md))
18. **Use `isPending` from mutation hooks** -- never use `formState.isSubmitting` (it only covers the synchronous `handleSubmit` wrapper, not the async mutation lifecycle); use `isPending` from `useMutation` instead
19. **Use `RhUi*` icons for action buttons** -- never use PatternFly icons like `PlusCircleIcon` directly; use `RhUiAddIcon`, `RhUiDuplicate`, etc. from `@patternfly/react-icons`
20. **CSS module classes over inline style objects** -- prefer `.module.css` classes over `style={{ ... }}` props; CSS modules are more DOM-efficient, cacheable, and keep styles co-located
21. **No mutable counters in `.map()`** -- do not use `let` counters inside `.map()` or `.forEach()`; pre-compute indices immutably or use the callback's index parameter
22. **`aria-label` only on interactive/widget/landmark elements** -- do not put `aria-label` on generic `<span>` or `<div>`; use it on buttons, inputs, `role="region"`, images, or landmarks
23. **Never use `eslint-disable`** -- do not add `eslint-disable` or `eslint-disable-next-line` to new or modified code. Every rule catches a real problem; fix the code so the rule passes. Pre-existing suppressions are tech debt being cleaned up. See [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §28
24. **Conditional hook execution uses wrapper components** -- hooks must be called unconditionally per React rules; if a hook's result is used conditionally, extract to a wrapper component that is conditionally rendered (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §29)
25. **Leverage existing libraries before custom code** -- all async server state must use TanStack Query (`useQuery`/`useMutation`/`useQueries`), not manual `useEffect` + `useState` + `fetch`; forms must use react-hook-form + Zod; styling must use PatternFly + CSS modules. Do not reimplement what the tech stack already provides (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §30)
26. **No `// TODO` comments in shipped code** -- deferred work belongs in an issue, not buried in source. If a follow-up is needed, create a ticket and reference it inline (e.g., `// Inline type until #12345`). See [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §32
27. **New routes must set `requiredPermissions` and/or `routePermission`** -- every route with access requirements needs permission fields in `navigationItems.tsx`; create/edit routes need a `routePermission` for `ProtectedRoute` guard (see [`docs/permissions-rbac.md`](docs/permissions-rbac.md))
28. **New write actions must use `DisabledWithTooltip` + permission hook** -- never expose ungated create/edit/delete buttons; use a domain `use*Permissions` hook and `permissionTooltip()` for copy (see [`docs/permissions-rbac.md`](docs/permissions-rbac.md))
29. **New permission-gated features need mock handlers** -- add role-aware responses in `packages/syntara-mock-api/src/handlers.ts` `can_i` block for all 4 roles (admin, viewer, auditor, user) and E2E tests in `permission-gating.spec.ts`
30. **Use `useDocLink` for documentation URLs** -- never hardcode doc URLs; use `useDocLink('workflows')` from `src/utils/docs/useDocLink.ts`; pass the result to `SynPageHeader`'s `docLink` prop; add new keys to `docsUrls.json` when adding new pages (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) section 33)
31. **No `new Date()` in mock API seed data** -- seed data in `packages/syntara-mock-api/src/resources/` and `utils/` must use deterministic timestamps from `mockDates.ts`, never `new Date()`. Dynamic timestamps cause visual regression baselines to go stale across CI runs because rendered dates change daily
32. **New pages must render `<title>{toPageTitle(['...'])}</title>`** -- every top-level page component (default export with `<SynPage>`) must render a `<title>` as its first `<SynPage>` child. Use `toPageTitle` from `src/utils/toPageTitle.ts`
33. **No new `forwardRef`** -- React 19 passes `ref` as a regular prop; accept `ref` on the props type instead of wrapping with `forwardRef` (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §38)
34. **Prefer ref callback cleanup functions** -- when attaching DOM listeners or observers, return a cleanup from the ref callback instead of pairing `useRef` + `useEffect` (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §38)
35. **No new `useContext`** -- React 19 reads context with `use(Context)`; do not add `useContext` (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §39)
36. **Prefer `useOptimistic` for clear toggle/counter mutations** -- update UI inside a `startTransition` Action with `mutateAsync`; do not hand-roll pending mirror state for simple before/after mutations (see [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) §40)

### Feature Preservation Rules

- Never remove existing features or UI elements unless explicitly instructed
- Before removing any component, function, or route, confirm with the user
- When rebasing or resolving conflicts, always prefer keeping both sides' features unless told otherwise
- If unsure whether something should be removed, ASK

### Documentation Must Stay in Sync with Code

**CRITICAL: Documentation must always reflect the current state of the codebase.**

- **When adding or changing code**: Review all related documentation (`docs/`, `README.md`, `AGENTS.md`, `DEVELOPER_GUIDE.md`, `CONTRIBUTING.md`, and any in-source `README.md` files) and update them to reflect the change. New features, renamed files, changed APIs, removed dependencies, or altered behavior must be documented immediately — not deferred.
- **During code review**: Verify that documentation is accurate and consistent with the code being reviewed. Flag any PR that changes behavior without updating the corresponding docs.
- **What to check**: Architecture docs, API client references, tech stack lists, command examples, file path references, code examples, cross-document links, and any "How to" guides.
- **No stale docs**: If a document references a file, dependency, function, or pattern that no longer exists, fix it or remove the reference. Dead links and outdated examples erode trust in the documentation.

## Essential Commands

```bash
# Development
npm start                  # Start all services (UI, mock API)
npm run start:ui           # Start UI only
npm run start:mock-api     # Start mock API only

# Testing
npm test                    # Run all tests
npm run test:ui             # Run UI package tests
npm run e2e                 # Run e2e playwright tests
npm run e2e:ui              # Run e2e playwright tests in the playwright UI
npm run e2e:visual-regression        # Page screenshot visual regression (mock API + UI via Playwright webServer)
npm run e2e:visual-regression:update # Same, with --update-snapshots (see packages/syntara-ui/VISUAL_REGRESSION.md)

# E2E test suite tags — Playwright tags that control where each test runs:
#   @pr-check      Fast critical-path tests; select with --grep @pr-check
#   @konflux-skip  Tests excluded from Konflux pipelines via --grep-invert @konflux-skip (flaky in that env only)
#   @local-only    Visual regression tests; excluded from all CI automatically
# Full rules: .claude/skills/frontend-playwright-e2e/SKILL.md → "Test Suite Tags"
#
# When to apply @konflux-skip:
#   - Test creates a real workflow execution and waits for Temporal to complete it
#     (approval flows, multi-step runs, badge checks) — Temporal under Konflux cluster
#     load frequently times out or returns unexpected states.
#   - Test has a wall-clock budget >25s; Konflux runner load regularly pushes it over.
#   - Test relies on the backend Temporal worker reaching an external URL (httpbin,
#     webhooks, LLM APIs) — the worker's network is more restricted than the test runner.
# How to apply:
#   test('name', { tag: ['@konflux-skip'] }, async ({ app }) => { ... })
#   After editing, run: npx --prefix .. prettier --write <file>
#   (Prettier may reformat to multi-line — that is correct and expected.)
# See also: root CLAUDE.md → "Konflux CI Environment" for backend skip patterns.

# Run a specific test or coverage
npx vitest run packages/syntara-ui/path/to/specific/test.test.ts
npm run test:coverage

# Build
npm run build              # Build UI package
npm run gen                # Regenerate API contracts

# Code Quality
npm run check              # Run all static analysis checks concurrently (mirrors CI "Checks" job)
npm run format             # Format code
npm run format:check       # Check formatting
npm run lint               # Run ESLint
npm run tsc                # Type check only
```

## Connecting to Real Backend

To use the real backend instead of the mock API:

1. The backend is available at `../backend/` in this monorepo
2. Follow the backend README (`../backend/README.md`) to start the API server
3. Export the backend URL and start the UI:

```bash
export VITE_API_URL=http://localhost:8000
npm start
```

## Architecture Documentation

For how the UI is structured, see these comprehensive guides:

- [`docs/architecture.md`](docs/architecture.md) - Main architecture guide covering routing, state management, the workflow builder, and [API filtering](docs/architecture.md#api-filtering-architecture)
- [`docs/data-flow.md`](docs/data-flow.md) - Deep dive into OpenAPI contract generation, type-safe API clients, and workflow transformations (nested ↔ flat)
- [`docs/zustand-architecture.md`](docs/zustand-architecture.md) - Workflow store details, state management patterns, and best practices
- [`docs/websocket-architecture.md`](docs/websocket-architecture.md) - WebSocket infrastructure, multi-channel architecture, and real-time features
- [`docs/execution-visualizer-protocol.md`](docs/execution-visualizer-protocol.md) - Execution visualizer WebSocket protocol, endpoints, and data structures
- [`docs/user-guides/filtering.md`](docs/user-guides/filtering.md) - End-user guide for search, filter types, and shareable filtered URLs

### Quick Navigation by Task

| Working on...                       | Read this                                                                                                                                                                                                                                                                                               |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **New here / onboarding**           | [`docs/ai-assisted-development.md`](docs/ai-assisted-development.md) -- AI agent prompts, screenshot workflow, full example                                                                                                                                                                             |
| **API integration**                 | [`docs/data-flow.md`](docs/data-flow.md) -- OpenAPI contracts and type-safe clients                                                                                                                                                                                                                     |
| **Workflow transformations**        | [`docs/data-flow.md`](docs/data-flow.md) -- Nested to flat conversions                                                                                                                                                                                                                                  |
| **Step registry (`NodeRegistry`)**  | [`docs/architecture.md`](docs/architecture.md) -- auto-discovery of step types                                                                                                                                                                                                                          |
| **Builder internals**               | [`docs/architecture.md`](docs/architecture.md) -- "Builder internals (advanced)"                                                                                                                                                                                                                        |
| **State management**                | [`docs/zustand-architecture.md`](docs/zustand-architecture.md) -- Zustand guide                                                                                                                                                                                                                         |
| **WebSocket / real-time**           | [`docs/websocket-architecture.md`](docs/websocket-architecture.md) -- multi-channel infrastructure                                                                                                                                                                                                      |
| **Execution visualization**         | [`docs/execution-visualizer-protocol.md`](docs/execution-visualizer-protocol.md) -- protocol, endpoints, data specs                                                                                                                                                                                     |
| **List filters / search**           | [`docs/architecture.md`](docs/architecture.md#api-filtering-architecture) -- FilterBar, `useCursorPagination`, types; [`docs/user-guides/filtering.md`](docs/user-guides/filtering.md) -- UX guide                                                                                                      |
| **PR sizing / stacking**            | [`.github/pull_request_template.md`](../.github/pull_request_template.md) -- PR template and guidelines                                                                                                                                                                                                 |
| **List page with pagination**       | [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) -- `useCursorPagination` pattern                                                                                                                                                            |
| **Full list (dropdowns, settings)** | [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) -- section 22: `fetchAllPages` + `useAll*` hooks (not `limit: 100` single queries)                                                                                                          |
| **Confirmation dialogs**            | [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) -- `NxConfirmationDialog` component; for content patterns (tier copy, checkbox labels, button labels) use Storybook MCP: `get-documentation` -> `"components-dialogs-nxconfirmationdialog"` |
| **Sonar S6478 / PF `toggle` props** | [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) -- nested components and PatternFly render props                                                                                                                                            |
| **Dialog state management**         | [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) -- `useDialogState` hook                                                                                                                                                                    |
| **Error handling patterns**         | [`docs/error-handling.md`](docs/error-handling.md) -- RFC 9457, error utilities, retry support                                                                                                                                                                                                          |
| **Testing standards**               | [`.claude/skills/frontend-testing-guidelines/SKILL.md`](../.claude/skills/frontend-testing-guidelines/SKILL.md) -- coverage, queries, accessibility                                                                                                                                                     |
| **Visual regression testing**       | [`packages/syntara-ui/VISUAL_REGRESSION.md`](packages/syntara-ui/VISUAL_REGRESSION.md) -- page registry, baselines, manual-only workflow                                                                                                                                                                |
| **New workflow step type**          | `packages/syntara-ui/src/routes/builder/registry/nodes/QUICK_START.md`                                                                                                                                                                                                                                  |
| **UX / PatternFly design system**   | [`.claude/skills/frontend-patternfly-ux/SKILL.md`](../.claude/skills/frontend-patternfly-ux/SKILL.md) -- PF6 patterns                                                                                                                                                                                   |
| **Library docs / llms.txt links**   | [`.claude/skills/frontend-library-references/SKILL.md`](../.claude/skills/frontend-library-references/SKILL.md) -- fetch before writing React, Zod, Zustand, Vitest, Vite, or TanStack Query code                                                                                                       |
| **Permission gating / RBAC**        | [`docs/permissions-rbac.md`](docs/permissions-rbac.md) -- `useCanI`, `DisabledWithTooltip`, `ProtectedRoute`, nav filtering, mock API roles, ungated inventory                                                                                                                                          |
| **Page content frame (`SynPanel`)** | `packages/syntara-ui/src/components/layout/SynPanel.tsx` -- `Panel` -> `PanelMain` -> `PanelMainBody`; see JSDoc (glass vs `opaqueFloatingFill` vs `variant="raised"`) and [patternfly-react#12372](https://github.com/patternfly/patternfly-react/pull/12372)                                          |
| **Documentation links**             | [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) -- `useDocLink` hook, `DocKey` type, community vs extended URL resolution                                                                                                                   |

### Quick Reference: Common Tasks

#### How do I make API calls?

Use the type-safe clients from `client.tsx`:

```typescript
import { workflowClient } from '../client'

const { data, isLoading, error } = workflowClient.useQuery('get', '/workflows')
const { mutate } = workflowClient.useMutation('post', '/workflows')
```

See: [`docs/data-flow.md`](docs/data-flow.md) — "Type-Safe API Clients"

#### How do I add a new route?

1. Add route constant to `packages/syntara-ui/src/app/AppRoute.tsx`
2. Add navigation item to `packages/syntara-ui/src/app/navigationItems.tsx` with lazy-loaded component
3. The router auto-discovers it from `navigationItems` — no manual route config needed
4. In the page component, render `<title>{toPageTitle(['Page Name'])}</title>` as the first child of `<SynPage>`; import `toPageTitle` from `src/utils/toPageTitle`

#### How do I add filters to a list page?

Use **`FilterBar` + `useCursorPagination`** (not a hand-rolled cursor/`useFilterState` stack). Keyword search is a TEXT field with `contains` applied on **Enter** or the **Apply filter** control — there is no separate free-standing search input on `FilterBar`.

1. **Define fields** in a colocated `*Filters.ts` / `*FilterDefinitions.ts` using `FilterFieldDefinition` + `FilterTypeEnum` / `FilterOperatorEnum` from `src/types/filters.ts`.
2. **Wire pagination + filters + sort** with `useCursorPagination` — it owns URL-synced filters, sort (`defaultSort` / `columns`), cursor reset, and `queryParams`.
3. **Render** `FilterBar` (or `NxListPanelToolbar`) with `fieldDefinitions`, `filters`, `onFilterChange={handleFilterChange}`, and `clearAllFilters={handleClearAllFilters}`.
4. **Query** with the typed client: `client.useQuery('get', '/resource', { params: { query: queryParams } })`.
5. **Empty filtered results** → `SynEmptyStateFilter` with clear-all; unfiltered empty → `SynEmptyStateNoData`.

```typescript
import { FilterBar } from '../../components/filters/FilterBar'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import type { FilterFieldDefinition } from '../../types/filters'
import type { SortableColumn } from '../../types/sorting'

const fieldDefinitions: FilterFieldDefinition[] = [
  {
    key: 'name',
    label: 'Keyword',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by keyword',
  },
]

const columns: SortableColumn[] = [{ field: 'name', label: 'Name', isSortable: true }]

function MyListPage() {
  const {
    cursor,
    setCursor,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
    getSortParams,
  } = useCursorPagination({
    defaultSort: { field: 'name', direction: 'asc' },
    columns,
  })

  const query = myClient.useQuery('get', '/items', { params: { query: queryParams } })
  const items = query.data?.resources ?? []
  useCursorReset(items.length, hasActiveFilters, cursor, query.isFetching, setCursor)

  return (
    <>
      <FilterBar
        fieldDefinitions={fieldDefinitions}
        filters={filters}
        onFilterChange={handleFilterChange}
        clearAllFilters={handleClearAllFilters}
      />
      {/* <Th sort={getSortParams('name')}>Name</Th> + getFooterProps(query.data) */}
    </>
  )
}
```

**Best practices for field definitions:**

- Prefer factory helpers (`getXFilterDefinition()`) when options are dynamic or shared.
- TEXT keyword/name fields: `defaultOperator: FilterOperatorEnum.CONTAINS`; apply on Enter or Apply filter.
- SELECT boolean-looking options stay as strings (`'true'`/`'false'`) until `transformFilters` converts them for the API.
- Use `asyncOptions` for server typeahead (for example executions → workflow picker).
- Put scoped params (`project_id`) in `useCursorPagination({ extraParams })`, not as fake filters.
- Confirm the backend supports the operator (`in`, date AND ranges, etc.) before exposing the UI control.

**`useFilteredQuery`** (`src/hooks/useFilteredQuery.ts`) builds filter query params and calls `client.useQuery` with `useQueryState`. Use it for filtered fetches **without** full list pagination. For list pages, prefer `useCursorPagination` + `client.useQuery`.

```typescript
import { useFilteredQuery } from '../../hooks/useFilteredQuery'
import { useFilterState } from '../../hooks/useFilterState'
import { detachPromise } from '../../utils/detachPromise'

const { filters } = useFilterState()
const { data, queryState, refetch } = useFilteredQuery({
  client: workflowClient,
  method: 'get',
  path: '/workflows',
  filters,
  limit: 20,
  includeTotalCount: true,
  errorOptions: {
    title: 'Error loading workflows',
    onRetry: () => detachPromise(refetch()),
  },
})
```

See: [`docs/architecture.md`](docs/architecture.md#api-filtering-architecture) · [`docs/user-guides/filtering.md`](docs/user-guides/filtering.md) · [`docs/TEST_HELPERS_FILTER_TESTING.md`](docs/TEST_HELPERS_FILTER_TESTING.md)

#### What is the default workflow name?

**`new-workflow`**, defined as `DEFAULT_WORKFLOW_NAME` in `packages/syntara-ui/src/routes/builder/utils/workflowNaming.ts`. Conflicts auto-increment: `new-workflow-1`, `new-workflow-2`, etc.

#### How do I debug the workflow builder?

- **React DevTools**: Inspect component props and Zustand state
- **Console**: `useWorkflowStore.getState()` to inspect workflow store
- Steps not appearing → check `NodeRegistry`; edges not connecting → verify handle IDs; state not updating → check store actions

#### How do I format dates?

For any **rendered/read-only** date or timestamp (table columns, detail views, tooltips), use `DateCell` / `UserTimestamp` (`packages/syntara-ui/src/components/table/DateCell.tsx`), which wrap PatternFly's `Timestamp` component (`dateFormat="medium" timeFormat="medium"`). For execution start/end ranges that collapse to time-only on the same day, use the `ExecutionTimestamp` helper. Do not call `toLocaleString()` or render date-fns output directly in JSX.

`packages/syntara-ui/src/utils/dateUtils.ts` is now scoped to non-display helpers and to the handful of **plain-string** contexts where JSX can't be used (dropdown option labels, `TextInput value=`, model fields):

- `formatDateForApi(date)` / `formatDateChipValue(isoValue)` — API/filter serialization
- `formatDateYMD(date)` / `parseDateYMD(val)` — round-trip helpers for PF `DatePicker`
- `formatElapsedTime(elapsedMs)` — "1h 2m 3s" (duration, not a calendar timestamp)
- `formatTimeAgo(isoString)` — relative "5m ago" labels (no PF `Timestamp` equivalent)
- `formatExpirationDate(isoString)` — plain-string date only, for `TextInput value=` contexts
- `formatDateTime(isoString?)` — kept only for plain-string contexts (e.g. dropdown option labels, version-name fallbacks) that cannot render JSX; do not call this from new component render paths — use `DateCell`/`Timestamp` instead

Use for UI display only, not in logic (per i18n guidelines). Trigger-specific interval formatting stays in `utils/triggerFormatting.ts`.

#### How do I add a documentation link to a page?

Use the `useDocLink` hook from `src/utils/docs/useDocLink.ts`:

```typescript
import { useDocLink } from '../../utils/docs/useDocLink'

function MyPage() {
  const docLink = useDocLink('workflows') // DocKey is type-safe — only keys from docsUrls.json
  return <SynPageHeader title="Workflows" docLink={docLink} />
}
```

The key passed to `useDocLink` must exist in `src/utils/docs/docsUrls.json` (flat path string per key). TypeScript enforces this at compile time. Community builds resolve every key to the shared README; extended builds resolve per-key URLs when configured. See [`.claude/skills/frontend-coding-standards/SKILL.md`](../.claude/skills/frontend-coding-standards/SKILL.md) section 33 for full details.

## Critical Development Workflows

- **Dependency Management**: PatternFly components consumed from npm; automatic rebuilds in watch mode; hot reloading for component changes
- **API Contract Generation**: Types generated from external OpenAPI specs, shared between UI and Mock API — update via `npm run gen`
- **Mocking Approach**: MSW (Mock Service Worker) for consistent API mocking in development and testing

## Performance Notes

- React Compiler for automatic optimization
- Vite for rapid builds
- Lazy loading of routes/components
- Vitest for lightweight testing

## Development Constraints

### Technical Boundaries

- Node.js 22+ required
- TypeScript 5.9
- React 19
- Vite build system
- npm workspaces

### Port Configuration (Development)

- UI: <http://localhost:5173>
- Mock API: <http://localhost:3000>
- Storybook (+ MCP server): <http://localhost:5174>
- WebSocket: derived from page origin (real backend only; override with `VITE_WS_URL` if needed)

E2E tests use different ports (UI: 4173, mock API: 3300) to avoid conflicts with a running dev server.

## Deployment Considerations

- **Containerization**: Podman (local), Docker Buildx (CI/CD)
- **Multi-architecture**: Supports linux/amd64 and linux/arm64
- **Production build**: Nginx-based (UI), Node.js (Mock API)
- **Authentication**: Basic (demo/coffee)
- **Separate containers**: UI and Mock API

### Container Commands

```bash
# Build containers
npm run podman:build              # Build all containers
npm run podman:build:ui           # Build UI container only
npm run podman:build:mock-api     # Build mock API container only

# Run containers
npm run podman:run                # Run all containers
npm run podman:run:ui             # Run UI on port 4000
npm run podman:run:mock-api       # Run API on port 3000
```
