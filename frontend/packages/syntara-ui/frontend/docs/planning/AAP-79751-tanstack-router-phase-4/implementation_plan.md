# AAP-79751: Phase 4 TanStack Router Migration - Low-Risk Implementation Plan

## Executive Summary

**Actual Scope**: 9 pages need conversion (not 5 as ticket states)
**Risk Level**: Medium - all pages have test coverage, but complex permission logic
**Recommended Approach**: 6 small PRs, grouped by similarity and complexity

---

## Ticket Issues Found

1. ❌ **Ticket claims User Detail & Credential Detail were converted in Phase 4** - BOTH still need work
2. ❌ **Missing pages**: Service Account Detail, Integration Detail not listed
3. ✅ **All other pages correctly identified**

---

## Recommended PR Sequence (Low Risk → High Risk)

### **PR #1: Settings Page** (Simplest - 1 tab)

**Risk**: ⭐ Very Low

- Single category-based navigation (not true tabs, but uses useUrlTab)
- Minimal conditional logic (2 conditional checks)
- 269 LOC - smallest scope
- Has comprehensive tests
- No permission-gated tabs

**Why first**: Establishes the pattern with minimal surface area

---

### **PR #2: Access Management Hub** (Simple - multi-tab navigation)

**Risk**: ⭐⭐ Low

- 9 tabs but all at same level (no nesting complexity)
- Permission-based tab visibility (24 permission checks)
- Well-tested (AccessManagement.test.tsx)
- 181 LOC - small file

**Why second**: Validates the pattern works for permission-gated tab lists

---

### **PR #3: Group Detail + Project Detail** (Moderate - similar patterns)

**Risk**: ⭐⭐⭐ Moderate

- **Group Detail**: 3 tabs, 358 LOC, 23 conditional tab checks
- **Project Detail**: 3 tabs, 283 LOC, 6 conditional tab checks
- Both have: Details tab + Assignments tab + one more (Members/Workflows)
- Similar permission patterns
- Both well-tested

**Why together**: Near-identical structure, can reuse conversion approach

---

### **PR #4: Service Account Detail** (Moderate - 3 tabs)

**Risk**: ⭐⭐⭐ Moderate

- 3 tabs, 347 LOC
- Minimal conditional logic (1 check)
- Well-tested
- Similar to Group/Project Detail

**Why standalone**: Slightly different from Group/Project, safer to isolate

---

### **PR #5: Integration Detail + Identity Provider Detail** (Complex - 2 tabs each but large files)

**Risk**: ⭐⭐⭐⭐ High

- **Integration Detail**: 2 tabs, 461 LOC, 11 permission checks
- **Identity Provider Detail**: 2 tabs, 495 LOC, 14 permission checks
- Larger files with complex business logic
- Both have OIDC/auth-related complexity

**Why together**: Both configuration-domain pages with similar complexity

---

### **PR #6: Credential Detail + User Detail** (Most Complex)

**Risk**: ⭐⭐⭐⭐⭐ Very High

- **Credential Detail**: 3 tabs, 498 LOC, uses old inline Tab pattern (not useUrlTab!)
- **User Detail**: 6 tabs (most complex!), 464 LOC, 16 conditional checks
- User Detail has: Details, Groups, Identities, Assignments, Check Access, My Permissions
- Both have complex state management and multiple query dependencies

**Why last**: Highest complexity, most tabs, most conditional logic. If these work, useUrlTab can be removed.

---

## Conversion Pattern (Apply to Each Page)

### Step 1: Create Route Structure

```
Before: /users/:userId/:tab
After:  /users/:userId (layout) + child routes
  - /users/:userId/details
  - /users/:userId/groups
  - /users/:userId/identities
  - etc.
```

### Step 2: Update AppRoute.tsx

Add individual routes for each tab

### Step 3: Update navigationItems.tsx

Add hidden child route entries

### Step 4: Convert Component

- Extract layout (header, breadcrumbs, toolbar)
- Move to `renderPanel={() => <Outlet />}` pattern
- Create individual tab component files
- Remove `useUrlTab` hook call
- Update `SynUrlTabs` props

### Step 5: Update Tests

- Update route paths in tests
- Test each tab route independently
- Verify breadcrumbs still work
- Verify permission gating still works

### Step 6: Manual Testing Checklist

- [ ] Navigate to each tab via URL
- [ ] Navigate via tab clicks
- [ ] Browser back/forward works
- [ ] Breadcrumbs update correctly
- [ ] Deep links work (e.g., /users/abc-123/groups)
- [ ] Permission-gated tabs hide/show correctly
- [ ] Tab badges update (Members count, etc.)

---

## Risk Mitigation Strategies

### 1. **Feature Flags** (Optional but Recommended)

Add a feature flag for each conversion:

```typescript
const USE_NESTED_ROUTES = import.meta.env.VITE_NESTED_ROUTES_ENABLED !== 'false'
```

Can rollback via env var without code deploy

### 2. **Test Coverage Requirements**

Each PR must:

- ✅ Maintain or improve test coverage
- ✅ Add E2E test for deep linking
- ✅ Add E2E test for tab navigation
- ✅ Verify all permission scenarios

### 3. **Incremental Rollout**

- Merge PRs 1-2, monitor for issues
- If stable after 1 week, proceed with PRs 3-4
- If stable after 1 week, proceed with PRs 5-6
- Remove `useUrlTab` hook only after ALL pages converted

### 4. **Regression Testing Focus Areas**

- URL state synchronization
- Breadcrumb updates
- Permission-gated visibility
- Query string preservation
- Browser history navigation

---

## Post-Conversion Cleanup (PR #7)

**Only after all 6 PRs are stable:**

1. Remove `useUrlTab` hook from codebase
2. Update `SynUrlTabs` to make `renderPanel` required
3. Remove backward compatibility code
4. Update documentation

---

## Estimated Effort

| PR  | Pages               | Est. Dev Time | Est. Test Time | Total     |
| --- | ------------------- | ------------- | -------------- | --------- |
| 1   | 1 (Settings)        | 2-3 hours     | 1-2 hours      | 0.5 day   |
| 2   | 1 (AccessMgmt)      | 3-4 hours     | 2 hours        | 0.75 day  |
| 3   | 2 (Group+Project)   | 6-8 hours     | 3-4 hours      | 1.5 days  |
| 4   | 1 (ServiceAcct)     | 3-4 hours     | 2 hours        | 0.75 day  |
| 5   | 2 (Integration+IdP) | 8-10 hours    | 4 hours        | 1.75 days |
| 6   | 2 (Credential+User) | 10-12 hours   | 4-5 hours      | 2 days    |
| 7   | Cleanup             | 2-3 hours     | 1 hour         | 0.5 day   |

**Total: ~7.75 days** (1.5 weeks for solo dev)

---

## Success Criteria

- ✅ All 9 pages converted to nested layout routes
- ✅ All existing tests passing
- ✅ No regressions in tab navigation
- ✅ No regressions in permission gating
- ✅ `useUrlTab` hook removed
- ✅ Documentation updated
- ✅ No production incidents related to routing

---

## Open Questions for Product Owner

1. **User Detail complexity**: 6 tabs is a lot. Should we consider redesigning this page?
2. **Service Account Detail**: Not in original ticket - confirm this should be included?
3. **Integration Detail**: Not in original ticket - confirm this should be included?
4. **Timeline**: Is 2-week timeline acceptable, or do we need to compress?
5. **Feature flags**: Do we want the ability to rollback individual pages?
