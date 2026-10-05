import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { expectPageTitle } from '../../test/pageTitle'

import Tasks from './Tasks'

vi.mock('../../hooks/useProjectSelector', () => ({
  useProjectSelector: () => ({
    selectedProjectId: null,
    stableProjectId: null,
    isAllProjects: true,
    projects: [],
    ProjectSelector: null,
  }),
}))

vi.mock('../../utils/docs/useDocLink', () => ({
  useDocLink: () => null,
}))

vi.mock('./useTasksTabAccess', () => ({
  useTasksTabAccess: () => ({
    visibleTabs: ['approvals', 'form-responses'],
    isChecking: false,
    isError: false,
    canViewTasks: true,
    canViewApprovals: true,
    canViewFormResponses: true,
  }),
  TASKS_TAB_APPROVALS: 'approvals',
  TASKS_TAB_FORM_RESPONSES: 'form-responses',
}))

vi.mock('../approvals/ApprovalsListPanel', async () => {
  const { SynListPanelView } = await import('../../components/panels/list/SynListPanel')
  const { SynEmptyStateNoData } = await import('../../components/states/SynEmptyStateNoData')
  return {
    default: ({ tabKey, tabLabel }: { tabKey?: string; tabLabel?: string }) => (
      <SynListPanelView
        tabKey={tabKey}
        tabLabel={tabLabel}
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty={true}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        noDataState={<SynEmptyStateNoData title="No approvals yet" description="No approvals." />}
        body={null}
      />
    ),
  }
})

vi.mock('./formResponses/FormResponsesListPanel', async () => {
  const { SynListPanelView } = await import('../../components/panels/list/SynListPanel')
  const { SynEmptyStateNoData } = await import('../../components/states/SynEmptyStateNoData')
  return {
    FormResponsesListPanel: ({ tabKey, tabLabel }: { tabKey?: string; tabLabel?: string }) => (
      <SynListPanelView
        tabKey={tabKey}
        tabLabel={tabLabel}
        isPending={false}
        error={null}
        onRetry={() => {}}
        isEmpty={true}
        hasActiveFilters={false}
        onClearAllFilters={() => {}}
        noDataState={<SynEmptyStateNoData title="No form responses yet" description="No form responses." />}
        body={null}
      />
    ),
  }
})

vi.mock('../../hooks/useUrlTab', () => ({
  useUrlTab: () => ['approvals'],
}))

describe('Tasks', () => {
  it('renders the Tasks heading', () => {
    render(<Tasks />)
    expect(screen.getByRole('heading', { level: 1, name: 'Tasks' })).toBeInTheDocument()
    expectPageTitle(['Tasks'])
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<Tasks />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
