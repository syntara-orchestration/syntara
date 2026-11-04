import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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

const mockUseDocLink = vi.hoisted(() => vi.fn(() => null))

vi.mock('../../utils/docs/useDocLink', () => ({
  useDocLink: mockUseDocLink,
}))

const mockUseTasksTabAccess = vi.hoisted(() =>
  vi.fn(() => ({
    visibleTabs: ['approvals', 'form-responses'],
    isChecking: false,
    isError: false,
    canViewTasks: true,
    canViewApprovals: true,
    canViewFormResponses: true,
  }))
)

vi.mock('./useTasksTabAccess', () => ({
  useTasksTabAccess: mockUseTasksTabAccess,
  TASKS_TAB_APPROVALS: 'approvals',
  TASKS_TAB_FORM_RESPONSES: 'form-responses',
}))

vi.mock('../approvals/ApprovalsListPanel', async () => {
  const { SynListPanelView } = await import('../../components/panels/list/SynListPanel')
  const { SynEmptyStateNoData } = await import('../../components/states/SynEmptyStateNoData')
  return {
    ApprovalsListPanel: ({ tabKey, tabLabel }: { tabKey?: string; tabLabel?: string }) => (
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

const mockUseUrlTab = vi.hoisted(() => vi.fn(() => ['approvals']))

vi.mock('../../hooks/useUrlTab', () => ({
  useUrlTab: mockUseUrlTab,
}))

describe('Tasks', () => {
  beforeEach(() => {
    mockUseDocLink.mockReturnValue(null)
    mockUseTasksTabAccess.mockReturnValue({
      visibleTabs: ['approvals', 'form-responses'],
      isChecking: false,
      isError: false,
      canViewTasks: true,
      canViewApprovals: true,
      canViewFormResponses: true,
    })
    mockUseUrlTab.mockReturnValue(['approvals'])
  })

  it('renders the Tasks heading', () => {
    render(<Tasks />)
    expect(screen.getByRole('heading', { level: 1, name: 'Tasks' })).toBeInTheDocument()
    expectPageTitle(['Tasks'])
  })

  it('renders the Form responses tab panel when that tab is active', () => {
    mockUseUrlTab.mockReturnValue(['form-responses'])
    render(<Tasks />)
    expect(screen.getByRole('tabpanel', { name: 'Form responses' })).toBeInTheDocument()
    expect(mockUseDocLink).toHaveBeenCalledWith('formResponses')
  })

  it('renders the Approvals tab panel when that tab is active', () => {
    render(<Tasks />)
    expect(screen.getByRole('tabpanel', { name: 'Approvals' })).toBeInTheDocument()
    expect(mockUseDocLink).toHaveBeenCalledWith('tasks')
  })

  it('renders only the Approvals tab when form responses are not permitted', () => {
    mockUseTasksTabAccess.mockReturnValue({
      visibleTabs: ['approvals'],
      isChecking: false,
      isError: false,
      canViewTasks: true,
      canViewApprovals: true,
      canViewFormResponses: false,
    })
    mockUseUrlTab.mockReturnValue(['approvals'])

    render(<Tasks />)
    expect(screen.getByRole('tab', { name: 'Approvals' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Form responses' })).not.toBeInTheDocument()
  })

  it('renders only the Form responses tab when approvals are not permitted', () => {
    mockUseTasksTabAccess.mockReturnValue({
      visibleTabs: ['form-responses'],
      isChecking: false,
      isError: false,
      canViewTasks: true,
      canViewApprovals: false,
      canViewFormResponses: true,
    })
    mockUseUrlTab.mockReturnValue(['form-responses'])

    render(<Tasks />)
    expect(screen.getByRole('tab', { name: 'Form responses' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Approvals' })).not.toBeInTheDocument()
    expect(screen.getByRole('tabpanel', { name: 'Form responses' })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<Tasks />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
