# AAP-79751: Phase 4 TanStack Router Migration Plan

**Jira ticket:** https://redhat.atlassian.net/browse/AAP-79751
**Created:** 2026-09-21
**Status:** PR 1 is implemented. The remaining work needs team approval.

## Purpose

Replace the remaining `useUrlTab` and inline-tab patterns with TanStack Router nested layout routes. A layout owns shared page UI and tabs. A child route owns the selected tab content.

## Scope correction

The ticket says that User Detail and Credential Detail were converted in Phase 4. They were not. Service Account Detail and Integration Detail are also missing from the ticket.

Nine pages need conversion.

| Page                     | Tabs | Complexity | Ticket status               |
| ------------------------ | ---: | ---------- | --------------------------- |
| Settings                 |    1 | Low        | Included                    |
| Access Management Hub    |    9 | Low        | Included                    |
| Group Detail             |    3 | Moderate   | Included                    |
| Project Detail           |    3 | Moderate   | Included                    |
| Service Account Detail   |    3 | Moderate   | Missing                     |
| Identity Provider Detail |    2 | High       | Included                    |
| Integration Detail       |    2 | High       | Missing                     |
| Credential Detail        |    3 | Very high  | Incorrectly marked complete |
| User Detail              |    6 | Very high  | Incorrectly marked complete |

All pages have existing test coverage.

## Delivery plan

| PR  | Scope                                              | Risk      | Estimate  | Status                       |
| --- | -------------------------------------------------- | --------- | --------- | ---------------------------- |
| 1   | Settings                                           | Very low  | 0.5 day   | Implemented in draft PR #615 |
| 2   | Access Management Hub                              | Low       | 0.75 day  | Planned                      |
| 3   | Group Detail and Project Detail                    | Moderate  | 1.5 days  | Planned                      |
| 4   | Service Account Detail                             | Moderate  | 0.75 day  | Planned                      |
| 5   | Integration Detail and Identity Provider Detail    | High      | 1.75 days | Planned                      |
| 6   | Credential Detail and User Detail                  | Very high | 2 days    | Planned                      |
| 7   | Remove `useUrlTab` and legacy `SynUrlTabs` support | Low       | 0.5 day   | After PRs 1-6 are stable     |

Estimated total: 7.75 days for one developer.

### Why this order

- PR 1 establishes the layout pattern with the smallest surface area.
- PR 2 validates it with many permission-controlled tabs.
- PRs 3 and 4 apply it to similar detail pages.
- PRs 5 and 6 defer authentication and high-state-complexity pages until the approach is stable.

## Completed work: PR 1

Settings now uses a nested route structure:

```text
/system-administration/settings             layout route
/system-administration/settings/:category   category child route
```

The layout owns loading, permissions, save state, the dirty-form guard, page header, and tabs. The child route renders the selected category through `Outlet`. Existing category deep links still work.

## Standard conversion pattern

### 1. Define the route tree

Convert a base route and generic tab parameter into a layout route with named child routes. Update `AppRoute.tsx`, `src/app/routes`, and hidden entries in `navigationItems.tsx` together.

```text
Before: /users/:userId/:tab

After:
/users/:userId              layout
/users/:userId/details      child
/users/:userId/groups       child
/users/:userId/identities   child
```

### 2. Convert the page to a layout

The layout keeps shared UI, queries needed for the header or tab labels, and visible-tab logic. It must not manually choose content with `activeTab === ...`.

```tsx
<SynListPanelTabs basePath={basePath} defaultTab="details" validTabs={validTabs} renderPanel={() => <Outlet />}>
  <Tab eventKey="details" title="Details" />
  <Tab eventKey="members" title="Members" />
</SynListPanelTabs>
```

### 3. Move content to child routes

Create one component per child route. Put route-specific queries in the child unless the layout also needs the data. TanStack Query deduplicates identical queries.

### 4. Preserve permission behavior and metadata

Build `validTabs` from user permissions in the layout. A protected child route must still render an access-denied state or no content when a user opens its URL directly. Keep badge and count queries in the layout when tab titles need them.

## Testing requirements for every implementation PR

- Keep existing unit tests passing.
- Add or update a test for each child route.
- Add E2E coverage for a direct child-route URL and tab navigation.
- Check browser back and forward navigation.
- Check breadcrumbs, query-string preservation, tab counts, and permission-controlled tab visibility.
- Run an axe check for every new component that renders UI.

Manual test checklist:

- [ ] Open each tab from a direct URL.
- [ ] Select each tab in the UI.
- [ ] Use browser back and forward.
- [ ] Check breadcrumbs.
- [ ] Check permission-controlled tabs for each applicable role.
- [ ] Check tab badges and counts.

## Risk controls

- Merge PRs 1 and 2, then monitor for one week before PRs 3 and 4.
- Monitor PRs 3 and 4 before PRs 5 and 6.
- Do not remove `useUrlTab` until every planned page is converted and stable.
- A per-page feature flag is optional if rollback without deployment is required:

```ts
const USE_NESTED_ROUTES = import.meta.env.VITE_NESTED_ROUTES_ENABLED !== 'false'
```

## Expected benefits

- One focused component per tab.
- Lazy-loaded tab content.
- Stable, URL-first deep links.
- Less manual URL and active-tab state handling.
- Smaller, more focused tests.
- Removal of `useUrlTab` technical debt after the migration.

## Open decisions

1. Confirm that Service Account Detail and Integration Detail are in scope.
2. Confirm that the staged rollout and approximate two-week timeline are acceptable.
3. Decide whether each page needs a rollback feature flag.
4. Consider a User Detail UX review because it has six tabs.

## Final acceptance criteria

- All nine pages use nested layout routes.
- All tab navigation, deep links, permissions, and breadcrumbs work without regression.
- E2E coverage exists for the converted page routes.
- `useUrlTab` has no consumers and is removed.
- `SynUrlTabs` requires the routed-panel pattern after compatibility code is no longer needed.
