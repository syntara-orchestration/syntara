import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import TasksAccessGate from './TasksAccessGate'

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

vi.mock('../../hooks/useUrlTab', () => ({
  useUrlTab: () => ['approvals'],
}))

vi.mock('./Tasks', () => ({
  default: () => <div>Tasks content</div>,
}))

const mockUseTasksTabAccess = vi.hoisted(() => vi.fn())

vi.mock('./useTasksTabAccess', () => ({
  useTasksTabAccess: () => mockUseTasksTabAccess(),
  TASKS_TAB_APPROVALS: 'approvals',
  TASKS_TAB_FORM_RESPONSES: 'form-responses',
}))

function renderGate() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  return render(
    <Wrapper>
      <TasksAccessGate />
    </Wrapper>
  )
}

describe('TasksAccessGate', () => {
  it('renders Tasks when the user can view tasks', () => {
    mockUseTasksTabAccess.mockReturnValue({
      visibleTabs: ['approvals'],
      isChecking: false,
      isError: false,
      canViewTasks: true,
    })

    renderGate()
    expect(screen.getByText('Tasks content')).toBeInTheDocument()
  })

  it('shows a permission error state with retry when checks fail', async () => {
    mockUseTasksTabAccess.mockReturnValue({
      visibleTabs: [],
      isChecking: false,
      isError: true,
      canViewTasks: false,
    })

    renderGate()
    expect(screen.getByText('Unable to verify permissions')).toBeInTheDocument()
    const invalidateSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(invalidateSpy).toHaveBeenCalled()
  })

  it('has no accessibility violations in the access-denied state', async () => {
    mockUseTasksTabAccess.mockReturnValue({
      visibleTabs: [],
      isChecking: false,
      isError: false,
      canViewTasks: false,
    })

    const { container } = renderGate()
    expect(await axe(container)).toHaveNoViolations()
  })
})
