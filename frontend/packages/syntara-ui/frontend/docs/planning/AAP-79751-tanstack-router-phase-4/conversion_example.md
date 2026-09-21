# Conversion Example: Group Detail (Moderate Complexity)

This shows the exact transformation needed for a typical detail page with 3 tabs.

---

## Current Implementation (Before)

### Route Structure

```typescript
// AppRoute.tsx
GroupDetail: '/system-administration/access-management/groups/:groupId',
GroupDetailTab: '/system-administration/access-management/groups/:groupId/:tab',
```

### navigationItems.tsx

```typescript
{
  label: 'Group Detail',
  path: AppRoute.AccessManagement.GroupDetail,
  hidden: true,
},
{
  label: 'Group Detail Tab',
  path: AppRoute.AccessManagement.GroupDetailTab,
  hidden: true,
},
```

### GroupDetail.tsx (Simplified)

```typescript
export function GroupDetail() {
  const { groupId } = useParams({ strict: false })
  const basePath = AppRoute.AccessManagement.GroupDetail.replace(':groupId', groupId ?? '')
  const [activeTab] = useUrlTab<GroupTab>(basePath)  // ❌ Remove this

  const validTabs = useMemo(() => {
    const tabs: string[] = ['details']
    if (showMembers) tabs.push('members')
    if (showAssignments) tabs.push('roles')
    return tabs
  }, [showMembers, showAssignments])

  return (
    <SynPage>
      <SynPageHeader title={groupData.name} breadcrumbs={...} toolbar={...} />
      <SynPageBody>
        <SynListPanel>
          <SynListPanelTabs
            basePath={basePath}
            defaultTab="details"
            validTabs={validTabs}
          >
            <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
            {showMembers && <Tab eventKey="members" title={<TabTitleText>Members</TabTitleText>} />}
            {showAssignments && <Tab eventKey="roles" title={<TabTitleText>Assignments</TabTitleText>} />}
          </SynListPanelTabs>

          {/* ❌ Manual tab content switching */}
          <GroupTabContent
            activeTab={activeTab}
            group={groupData}
            showMembers={showMembers}
            showAssignments={showAssignments}
          />
        </SynListPanel>
      </SynPageBody>
    </SynPage>
  )
}

function GroupTabContent({ activeTab, group, showMembers, showAssignments }) {
  return (
    <>
      {activeTab === 'details' && <GroupDetailsTab group={group} />}
      {activeTab === 'members' && showMembers && <GroupMembersPanel groupId={group.id} />}
      {activeTab === 'roles' && showAssignments && <RoleAssignmentsPanel principalId={group.id} />}
    </>
  )
}
```

---

## New Implementation (After)

### Route Structure

```typescript
// AppRoute.tsx
GroupDetail: '/system-administration/access-management/groups/:groupId',  // Layout route
GroupDetailDetails: '/system-administration/access-management/groups/:groupId/details',
GroupDetailMembers: '/system-administration/access-management/groups/:groupId/members',
GroupDetailRoles: '/system-administration/access-management/groups/:groupId/roles',
```

### navigationItems.tsx

```typescript
{
  label: 'Group Detail',
  path: AppRoute.AccessManagement.GroupDetail,
  hidden: true,
  lazy: () => import('./routes/access-management/groups/GroupDetailLayout'),
  children: [
    {
      label: 'Group Details',
      path: AppRoute.AccessManagement.GroupDetailDetails,
      hidden: true,
      lazy: () => import('./routes/access-management/groups/GroupDetailsTab'),
    },
    {
      label: 'Group Members',
      path: AppRoute.AccessManagement.GroupDetailMembers,
      hidden: true,
      lazy: () => import('./routes/access-management/groups/GroupMembersTab'),
    },
    {
      label: 'Group Roles',
      path: AppRoute.AccessManagement.GroupDetailRoles,
      hidden: true,
      lazy: () => import('./routes/access-management/groups/GroupRolesTab'),
    },
  ],
},
```

### GroupDetailLayout.tsx (New file - the layout)

```typescript
import { Outlet } from '@tanstack/react-router'

export default function GroupDetailLayout() {
  const { groupId } = useParams({ strict: false })
  const basePath = AppRoute.AccessManagement.GroupDetail.replace(':groupId', groupId ?? '')
  // ✅ No useUrlTab call!

  const validTabs = useMemo(() => {
    const tabs: string[] = ['details']
    if (showMembers) tabs.push('members')
    if (showAssignments) tabs.push('roles')
    return tabs
  }, [showMembers, showAssignments])

  // Early returns for loading/error states
  if (groupQuery.error) {
    return <DetailPageShell title="Group Details" breadcrumbs={...}>
      <GroupNotFoundState />
    </DetailPageShell>
  }

  if (!groupData) return null

  return (
    <SynPage>
      <SynPageHeader title={groupData.name} breadcrumbs={...} toolbar={...} />
      <SynPageBody>
        <SynListPanel>
          <SynListPanelTabs
            basePath={basePath}
            defaultTab="details"
            validTabs={validTabs}
            renderPanel={() => <Outlet />}  // ✅ Key change!
          >
            <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
            {showMembers && <Tab eventKey="members" title={<TabTitleText>Members</TabTitleText>} />}
            {showAssignments && <Tab eventKey="roles" title={<TabTitleText>Assignments</TabTitleText>} />}
          </SynListPanelTabs>
          {/* ✅ No manual tab content - handled by Outlet! */}
        </SynListPanel>
      </SynPageBody>
    </SynPage>
  )
}
```

### GroupDetailsTab.tsx (New file - details route)

```typescript
export default function GroupDetailsTab() {
  const { groupId } = useParams({ strict: false })

  // Query for group data (or get from parent context if we add one)
  const groupQuery = accessClient.useQuery(
    'get',
    '/groups/{group_id}',
    { params: { path: { group_id: groupId ?? '' } } },
    { enabled: !!groupId }
  )

  if (!groupQuery.data) return null

  return (
    <DescriptionList isHorizontal isAutoColumnWidths>
      <DescriptionListGroup>
        <DescriptionListTerm>Name</DescriptionListTerm>
        <DescriptionListDescription>{groupQuery.data.name}</DescriptionListDescription>
      </DescriptionListGroup>
      {/* ... rest of details ... */}
    </DescriptionList>
  )
}
```

### GroupMembersTab.tsx (New file - members route)

```typescript
export default function GroupMembersTab() {
  const { groupId } = useParams({ strict: false })

  return <GroupMembersPanel groupId={groupId ?? ''} onMembershipChange={...} />
}
```

### GroupRolesTab.tsx (New file - roles route)

```typescript
export default function GroupRolesTab() {
  const { groupId } = useParams({ strict: false })

  return (
    <RoleAssignmentsPanel
      principalType={RolePrincipalType.GROUP}
      principalId={groupId ?? ''}
      tabKey="roles"
      tabLabel="Assignments"
    />
  )
}
```

---

## Key Differences Summary

| Aspect              | Before                           | After                          |
| ------------------- | -------------------------------- | ------------------------------ |
| **Route structure** | 2 routes (base + :tab param)     | 4 routes (layout + 3 children) |
| **Tab switching**   | Manual `activeTab === 'x'` logic | Automatic via `<Outlet />`     |
| **useUrlTab**       | Required                         | Not used                       |
| **File structure**  | 1 large file                     | 1 layout + N tab files         |
| **Data fetching**   | All in parent                    | Can be per-tab or shared       |
| **Code splitting**  | Single bundle                    | Lazy-loaded per tab            |

---

## Benefits of New Approach

1. **Better code organization** - Each tab is its own file
2. **Lazy loading** - Tabs load on-demand, not upfront
3. **URL-first routing** - Deep links work automatically
4. **Type safety** - Route params typed by TanStack Router
5. **Simpler testing** - Test each tab route independently
6. **Better DX** - No manual tab switching logic

---

## Migration Gotchas

### 1. **Data Sharing Between Layout & Tabs**

**Problem**: Both layout and tabs need the same query data (e.g., group details for breadcrumb + content)

**Solution Options**:

- **Option A**: Duplicate queries (TanStack Query dedupes automatically)
- **Option B**: Add React Context at layout level
- **Option C**: Use TanStack Router's `loader` feature (future)

**Recommendation**: Start with Option A (duplicate queries), optimize later if needed.

### 2. **Permission-Gated Tabs**

**Problem**: Tabs that are conditionally shown based on permissions

**Solution**: Keep `validTabs` logic in layout, tabs render `null` if permission denied

```typescript
// Layout
const validTabs = useMemo(() => {
  const tabs = ['details']
  if (canReadMembers) tabs.push('members')
  return tabs
}, [canReadMembers])

// Tab component
export default function GroupMembersTab() {
  const { canReadMembers } = usePermissions()

  if (!canReadMembers) {
    return <SynEmptyStateAccessDenied />
  }

  return <GroupMembersPanel />
}
```

### 3. **Tab Badges (Counts)**

**Problem**: Tab titles show counts (e.g., "Members (5)")

**Solution**: Keep count queries in layout, pass via Tab props

```typescript
// Layout
const membersQuery = accessClient.useQuery(...)
const memberCount = membersQuery.data?.total ?? 0

<Tab eventKey="members" title={
  <TabTitleText>Members <Badge isRead>{memberCount}</Badge></TabTitleText>
} />
```

### 4. **Tests**

**Problem**: Tests navigate to `/groups/123/members` but expect component to work

**Solution**: Update test setup to mock TanStack Router context

```typescript
// Before
render(<GroupDetail />, {
  wrapper: createTestRouter({ route: '/groups/123/members' })
})

// After
render(<GroupMembersTab />, {
  wrapper: createTestRouter({
    route: '/groups/123/members',
    params: { groupId: '123' }
  })
})
```
