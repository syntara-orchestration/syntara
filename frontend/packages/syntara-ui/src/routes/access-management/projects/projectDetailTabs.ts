type ProjectTab = 'details' | 'workflows' | 'role-assignments'

const ALL_PROJECT_TABS: ProjectTab[] = ['details', 'workflows', 'role-assignments']
const PERMISSION_GATED_TABS = new Set<ProjectTab>(['workflows', 'role-assignments'])

export type ProjectTabState = {
  visibleTabs: ProjectTab[]
  urlValidTabs: ProjectTab[]
}

export function computeProjectTabState(
  canReadWorkflows: boolean,
  canReadAssignments: boolean,
  permissionsLoading: boolean,
  activeTab: ProjectTab
): ProjectTabState {
  if (permissionsLoading) {
    const urlValidTabs: ProjectTab[] = ['details']
    if (PERMISSION_GATED_TABS.has(activeTab)) {
      urlValidTabs.push(activeTab)
    }
    return { visibleTabs: ['details'], urlValidTabs }
  }

  const tabPermissions: Record<string, boolean> = {
    workflows: canReadWorkflows,
    'role-assignments': canReadAssignments,
  }
  const visibleTabs = ALL_PROJECT_TABS.filter((tab) => tabPermissions[tab] ?? true)
  return { visibleTabs, urlValidTabs: visibleTabs }
}

export function canShowTabContent(
  tab: ProjectTab,
  visibleTabs: ProjectTab[],
  permissionsLoading: boolean,
  activeTab: ProjectTab
): boolean {
  return visibleTabs.includes(tab) || (permissionsLoading && activeTab === tab)
}

export type { ProjectTab }
