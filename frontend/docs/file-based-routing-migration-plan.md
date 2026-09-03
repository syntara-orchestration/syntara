# File-based TanStack Router migration plan

## Goal

Move the UI from code-based TanStack Router definitions to file-based route
definitions without changing its browser URLs by accident.

Start with a complete route validation. Run the same validation after the
migration. Every difference must be intentional, covered by a redirect/alias,
or fixed as a regression.

## Current state

The UI currently has:

- 47 `createRoute()` definitions across 10 files under
  `packages/syntara-ui/src/app/routes/`.
- A manually assembled tree in
  `packages/syntara-ui/src/app/tanstackRouteTree.tsx`.
- A centralized `packages/syntara-ui/src/app/AppRoute.tsx` catalog used by
  navigation, breadcrumbs, tests, and imperative links.
- Navigation metadata in `navigationItems.tsx`.
- A visual-regression page registry containing a subset of concrete URLs.
- Lazy-loaded page components that should mostly remain unchanged.

The route definitions use TanStack parameter syntax (`$id`). Some `AppRoute`
helpers use Wouter-style placeholders (`:id`). The validator must treat both
forms as the same parameter without changing the real URL.

## Phase 0: establish the pre-migration route baseline

This phase must finish before the refactor starts.

### 0.1 Identify every route source

Inventory routes from all relevant sources, including:

- TanStack `createRoute()` definitions.
- `AppRoute` constants.
- `navigationItems.tsx` entries, including hidden/detail routes.
- Redirect and fallback routes.
- Breadcrumb and path-builder helpers.
- Visual-regression/page-registry entries.
- Literal URLs passed to links, navigation calls, redirects, or test fixtures.
- Any documented or externally supported URLs found in UI documentation.

Record the source file and line for each entry. This makes missing and duplicate
routes easy to fix.

### 0.2 Normalize the route contract

Create a deterministic route representation containing at least:

```json
{
  "template": "/system-administration/access-management/users/$userId",
  "parameters": ["userId"],
  "kind": "page",
  "source": "packages/syntara-ui/src/app/routes/access-management.tsx"
}
```

Use these normalization rules:

- Convert `:userId` and `$userId` to one canonical parameter syntax.
- Preserve parameter names and ordering.
- Distinguish static, parameterized, catch-all, redirect, and fallback routes.
- Record query/search parameters separately from pathname templates.
- Record whether a route is hidden from navigation; hidden does not mean
  unsupported.
- Sort entries deterministically.

Do not compare the generated route-tree file byte for byte. Imports and
formatting can change without changing the URL contract. Compare a normalized
route projection instead.

### 0.3 Validate route completeness and consistency

The baseline check should fail or produce a reviewed exception for:

- A route in one source that is absent from the others where parity is
  expected.
- Duplicate or ambiguous route templates.
- Navigation paths that do not match a registered route.
- Breadcrumb/path helpers that construct an unregistered template.
- Page-registry URLs that no longer resolve.
- Registered routes with no appropriate page-registry or smoke-test coverage.

Not every source needs to contain every route. Document the expected
relationship between sources so intentional omissions are not mistaken for
drift.

### 0.4 Probe concrete browser URLs

Route templates do not prove that pages render. Build a concrete URL probe set
containing:

- Every static route.
- Representative values for every parameterized route.
- Every detail/tab route represented in the page registry.
- Redirect source and destination URLs.
- Representative supported search-parameter combinations.
- Authenticated routes under the relevant test roles.

Run the probes against the pre-migration application with the existing
Playwright/mock-API setup. Record:

- HTTP/document load success.
- Final URL after redirects.
- Presence of the expected page/title or stable page landmark.
- Console/page errors.
- Access-denied behavior where permission gating is intentional.

Do not require every parameter value to exist in the database. Use deterministic
fixtures and distinguish route-matching failures from expected missing-resource
responses.

### 0.5 Commit the baseline artifact

Store a reviewable baseline containing:

- The normalized route manifest.
- The concrete probe list.
- Redirect/fallback expectations.
- Known intentional aliases or exceptions.
- The command used to regenerate and validate it.

CI must be able to reproduce the baseline from the pre-migration revision. Do
not depend on the current date or unstable API seed data.

## Phase 1: prepare file-based routing

1. Confirm that the TanStack Router and router-plugin versions are compatible.
2. Configure the router plugin and a dedicated route directory. The existing
   `src/routes/` contains feature components, so avoid creating ambiguity
   between feature folders and route-definition files.
3. Start with flat file-based routes or decide to introduce nested
   layout routes. Flat files are the safer first step because they minimize
   URL and `<Outlet />` changes.
4. Define the generated route-tree output location and commit policy.
5. Preserve the current root route, fallback behavior, redirects, and router
   provider configuration.

## Phase 2: migrate route definitions incrementally

Convert one route group at a time. Each file should use
`createFileRoute('/canonical/path')`. Keep the current page component,
lazy-loading, search validation, permission guard, loading state, and error
boundary.

For each migrated group:

1. Preserve the exact public pathname template.
2. Preserve parameter names and parameter semantics.
3. Preserve search/query validation and default behavior.
4. Preserve redirects and route ordering where matching precedence matters.
5. Regenerate `routeTree.gen.ts`.
6. Run the route completeness check and the affected concrete URL probes.
7. Run the affected unit, E2E, and visual-regression tests.

Keep migration changes separate from unrelated page or UX changes. This makes
route differences easier to review.

## Phase 3: reconcile route consumers

After migrating the route definitions:

- Make generated TanStack route paths the authoritative route source.
- Decide whether `AppRoute` remains as a compatibility/helper layer or is
  replaced by typed route helpers.
- Remove duplicated path literals only after equivalent generated routes and
  tests exist.
- Update imperative navigation and path builders to use typed route targets
  where practical.
- Keep public URL aliases and redirects explicit rather than hiding them in
  string replacement helpers.
- Verify breadcrumbs, navigation metadata, permissions, auth callbacks, and
  visual-regression registry entries.

## Phase 4: post-migration validation

Run the exact Phase 0 process against the migrated revision:

1. Re-inventory every route source.
2. Regenerate the normalized route manifest.
3. Compare it with the pre-migration baseline.
4. Rerun all concrete URL probes using the same fixture data and roles.
5. Compare final URLs, page landmarks/titles, console errors, and expected
   permission behavior.
6. Rerun completeness, unit, E2E, and visual-regression checks.

The migration is complete when:

- Every pre-migration supported URL still resolves to the same page or to an
  explicitly approved replacement/redirect.
- No route template, parameter, search contract, redirect, or fallback changed
  unintentionally.
- Every new file-based route is represented in the normalized manifest.
- Any intentional difference is documented with its compatibility behavior.
- The generated route tree is reproducible in a clean checkout.

## Phase 5: make route compatibility a permanent CI check

After the migration is stable, add a CI workflow that:

1. Generates the route tree.
2. Generates the normalized route projection.
3. Compares the pull request projection with the target branch.
4. Reports additions, removals, parameter changes, search-contract changes,
   and redirect changes.
5. Fails by default for removals or incompatible changes.
6. Requires an explicit reviewed migration/redirect entry for intentional
   breaks.
7. Runs the route probe suite for all affected routes, with a scheduled full
   suite as additional protection.

With file-based routing, `routeTree.gen.ts` is the router's structural
manifest. A normalized projection is still useful for CI because it avoids
diffing component imports and can include compatibility data that TanStack
Router does not define.

## Decisions to make before implementation

- Which URLs are public compatibility commitments versus internal-only routes?
- Are hidden/detail routes included? Recommended: yes if bookmarkable or
  linkable.
- Is renaming a parameter breaking? Recommended: yes.
- Are search-parameter additions/removals breaking? Define this per parameter;
  required changes should be breaking.
- Which redirects and aliases are supported, and for how long?
- Which roles and deterministic fixtures are required for authenticated probes?
- Should route changes fail CI immediately or initially produce warnings during
  a short adoption period?

## Deliverables

- Pre-migration route inventory and normalized baseline.
- Deterministic concrete URL probe list and results.
- File-based route definitions and committed generated route tree.
- Updated route consumers and tests.
- Post-migration comparison report with every difference classified.
- Permanent CI route-compatibility checker and documentation.
