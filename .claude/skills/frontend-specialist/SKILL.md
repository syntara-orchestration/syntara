---
description: "Standards for implementing, reviewing, and refactoring frontend code — React 19, TypeScript 5.9+, PatternFly 6, Vitest."
user-invocable: false
---

# Claude Skill: Frontend Specialist

Standards for implementing, reviewing, and refactoring frontend code using React 19, TypeScript 5.9+, PatternFly 6, Vite, and Vitest. Ensures production-grade code with exceptional testability, readability, and error resilience.

---

## CRITICAL: Read Project Standards Before Writing Code

**Before implementing ANY code**, read these project skill files:

1. **`.claude/skills/frontend-coding-standards/SKILL.md`** — API integration rules, form patterns, shared hooks (`useCursorPagination`, `useDialogState`, `useDeleteAction`, `NxConfirmationDialog`), PatternFly guidelines, i18n rules, and enum constant usage.

2. **`.claude/skills/frontend-testing-guidelines/SKILL.md`** — Testing rules (userEvent over fireEvent, accessible queries, vitest-axe), coverage requirements (80%), AAA pattern, and accessibility testing at three levels.

3. **`.claude/skills/frontend-library-references/SKILL.md`** — `llms.txt` URLs and official docs for all frontend libraries (React, Zod, Zustand, Vitest, Vite, TanStack Query/Router, React Flow, Storybook, dnd-kit, and more). **Fetch the relevant URL(s) before writing code against any of those libraries** — do not rely on training-data knowledge alone for libraries with breaking changes across major versions.

**Accessibility is mandatory in every task:** Always explicitly consider accessibility — semantics, labels, roles, keyboard interaction, focus management, and tests (Testing Library query order, `jsx-a11y`, vitest-axe). Do not ship or approve UI changes without an accessibility pass.

---

## Core Standards

### React 19

- Use functional components exclusively with proper hook patterns
- Accept `ref` as a regular prop — do **not** use `forwardRef` ([ref as a prop](https://react.dev/blog/2024/12/05/react-19#ref-as-a-prop))
- Prefer ref callback cleanup functions over paired `useRef` + `useEffect` for DOM listener/observer lifecycle ([cleanup functions for refs](https://react.dev/blog/2024/12/05/react-19#cleanup-functions-for-refs)); see coding standards §38
- Prefer `use(Context)` over `useContext(Context)` ([`use`](https://react.dev/reference/react/use)); see coding standards §39
- For clear before/after mutations (toggles, counters), prefer `useOptimistic` inside a `startTransition` Action ([`useOptimistic`](https://react.dev/reference/react/useOptimistic)); see coding standards §40
- Implement proper component composition over prop drilling
- Apply memoization strategically — only when profiling indicates performance issues
- Use proper error boundaries for graceful error handling
- Prefer controlled components for forms using react-hook-form
- Follow the Single Responsibility Principle

### TypeScript

- Leverage type inference where possible, explicit types where clarity demands
- Create discriminated unions for state machines and variant types
- Use `as const` for literal type narrowing
- Leverage utility types (Partial, Pick, Omit, Record) appropriately

### PatternFly 6

- Follow PatternFly 6 component patterns and accessibility standards
- Use PatternFly's layout components (Stack, Flex, Grid) for consistent spacing. Re-usable components should never have their own baked-in margin.
- ESLint enforces PF6 design tokens (`syntara/use-design-tokens-not-hardcoded`) and PF text/list components (`syntara/prefer-pf-text-components`, `syntara/prefer-pf-list-components`) at error level

### Vitest Testing

- Follow AAA pattern (Arrange-Act-Assert) for every test
- Test user behavior, not implementation details
- Use Testing Library queries in priority order: `getByRole` > `getByLabelText` > `getByPlaceholderText` > `getByText` > `getByTestId` (last resort)
- Every new component must have a `vitest-axe` `toHaveNoViolations()` test
- 80% coverage threshold on all new/modified files

---

## Pre-Submission Checklist

**Before delivering any implementation, verify ALL of these. These are the issues most frequently caught in PR reviews:**

### API & Error Handling

- [ ] No raw `fetch()` — all API calls use typed clients from `client.tsx`
- [ ] `useQueryState` uses object form with `{ title, onRetry }` — use `detachPromise(query.refetch())`, not `void`
- [ ] No unsafe `as` casts on API responses — use typed responses or type guards
- [ ] Errors displayed via `NxErrorState` component -- no raw error markup
- [ ] Mutations use `useMutationErrorHandler` or `useFormMutationErrorHandler`

### Forms

- [ ] Forms use Zod + react-hook-form with `zodResolver` -- no manual `useState` per field AKA controlled inputs
- [ ] Edit modals reset form via `useEffect` keyed on `[isOpen, item]`
- [ ] Loading states use `isPending` from mutation hooks -- not `formState.isSubmitting`

### Testing

- [ ] New components have `vitest-axe` tests with `toHaveNoViolations()` -- including expanded/interactive states
- [ ] Tests use `userEvent.setup()` -- no `fireEvent` (exception: `fireEvent.submit` when no submit button exists)
- [ ] Tests use accessible queries -- `getByRole` > `getByLabelText` > `getByText`; `getByTestId` only as last resort; never `querySelector`
- [ ] Tests use `within()` to scope assertions to specific containers (dialog footer, select, form group)
- [ ] Test names accurately describe what is asserted -- no misleading or duplicate names

### Code Organization

- [ ] No duplicated dialogs/logic -- use `NxConfirmationDialog`, `useDialogState`, `useDeleteAction`
- [ ] List views use `useCursorPagination` -- no manual cursor state
- [ ] File/function within ESLint size limits -- extraction preferred over suppression
- [ ] Enum constants from `@syntara/contracts` -- no string literals for discriminators
- [ ] CSS module classes over inline style objects -- more DOM-efficient and cacheable
- [ ] `RhUi*` icons for all action buttons -- not PatternFly icons like `PlusCircleIcon`
- [ ] No `eslint-disable` or `eslint-disable-next-line` in new/modified code -- fix the code so every rule passes; pre-existing suppressions are tech debt being cleaned up
- [ ] No `// TODO` / `// FIXME` comments -- track deferred work in an issue, not code
- [ ] All async server state uses TanStack Query (`useQuery`/`useMutation`/`useQueries`) -- no manual `useEffect` + `useState` for API calls (see .claude/skills/frontend-coding-standards/SKILL.md §30)
- [ ] Hooks called unconditionally but used conditionally -- extract to wrapper component (see .claude/skills/frontend-coding-standards/SKILL.md §29)

### Permission Gating

- [ ] New pages with access requirements: set `requiredPermissions` in `navigationItems.tsx`
- [ ] Create/edit routes: set `routePermission` for `ProtectedRoute` guard
- [ ] New CRUD actions: wrap in `DisabledWithTooltip` with domain permission hook and `permissionTooltip()`
- [ ] New permission-gated features: add role-aware mock handlers in `handlers.ts` for all 4 roles
- [ ] See [`frontend/docs/permissions-rbac.md`](../../frontend/docs/permissions-rbac.md) for architecture

### Documentation Links

- [ ] Pages with `SynPageHeader` pass `docLink={useDocLink('key')}` — no hardcoded doc URLs
- [ ] New pages have a corresponding entry in `src/utils/docs/docsUrls.json`

### PR Completeness

- [ ] UI changes include screenshots or screen recordings
- [ ] New API endpoints have mock handlers in `frontend/packages/syntara-mock-api/src/handlers.ts`
- [ ] It is the responsibility of the PR creator to _prove their change works_ — not the reviewer.

---

## Implementation Workflow

1. **Read the skills** — `.claude/skills/frontend-coding-standards/SKILL.md`, `.claude/skills/frontend-testing-guidelines/SKILL.md`, and `.claude/skills/frontend-library-references/SKILL.md` (fetch the relevant `llms.txt` URLs for any library you will use)
2. **Check for reusability** — Search `frontend/packages/syntara-ui/src/components/` and PatternFly docs before creating new components
3. **Implement incrementally** — Happy path first, then edge cases
4. **Write tests concurrently** — Tests alongside implementation
5. **Verify accessibility** — Keyboard navigation, ARIA attributes, axe tests
6. **Run quality checks** — `npm run lint`, `npm run tsc`, `npm test`

---

## Quality Gates

Code must meet these standards before delivery:

1. Zero TypeScript errors
2. All tests pass, new tests written for new features
3. No new ESLint warnings or errors -- rules at `warn` level will become `error`; treat them as errors now
4. Prettier formatting applied
5. WCAG 2.1 AA accessibility standards met
