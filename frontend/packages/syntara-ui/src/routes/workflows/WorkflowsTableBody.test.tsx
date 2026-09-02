import type { WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../access/accessClient'

import type { WorkflowRowActionCallbacks } from './workflowRowActions'
import { FlatWorkflowsTableBody, GroupedWorkflowsTableBody } from './WorkflowsTableBody'

vi.mock('../access/accessClient', () => ({
  accessFetchClient: { POST: vi.fn() },
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access-management/useProjectPermissions', () => ({
  useProjectPermissions: () => ({
    canCreate: false,
    canUpdate: false,
    canDelete: false,
    isLoading: false,
    tooltips: { create: '', update: '', delete: '' },
  }),
}))

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

const baseWorkflow: Workflow = {
  id: 'wf-1',
  name: 'Deploy Pipeline',
  is_builtin: false,
  published_version_id: null,
  project_id: 'proj-1',
} as Workflow

const rowActionCallbacks: WorkflowRowActionCallbacks = {
  navigate: vi.fn() as never,
  onRun: vi.fn(),
  onDuplicate: vi.fn(),
  onExport: vi.fn(),
  onPublish: vi.fn(),
  onUnpublish: vi.fn(),
  onDelete: vi.fn(),
  isDuplicating: false,
}

const isWorkflowProjectBuiltin = vi.fn(() => false)

function renderInTable(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <table>{ui}</table>
    </QueryClientProvider>
  )
}

describe('WorkflowsTableBody', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } } as never)
  })

  describe('GroupedWorkflowsTableBody', () => {
    it('renders project group header with workflow rows', () => {
      const grouped = new Map([
        ['proj-1', { project: { id: 'proj-1', name: 'Project Alpha' } as never, workflows: [baseWorkflow] }],
      ])

      renderInTable(
        <GroupedWorkflowsTableBody
          groupedWorkflows={grouped}
          collapsedProjects={new Set()}
          onToggleProject={vi.fn()}
          isWorkflowProjectBuiltin={isWorkflowProjectBuiltin}
          rowActionCallbacks={rowActionCallbacks}
        />
      )

      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      expect(screen.getByText('Deploy Pipeline')).toBeInTheDocument()
    })

    it('renders "No project" header for unknown project id', () => {
      const grouped = new Map([['unknown', { project: null, workflows: [baseWorkflow] }]])

      renderInTable(
        <GroupedWorkflowsTableBody
          groupedWorkflows={grouped}
          collapsedProjects={new Set()}
          onToggleProject={vi.fn()}
          isWorkflowProjectBuiltin={isWorkflowProjectBuiltin}
          rowActionCallbacks={rowActionCallbacks}
        />
      )

      expect(screen.getByText('No project')).toBeInTheDocument()
      expect(screen.getByText('Deploy Pipeline')).toBeInTheDocument()
    })

    it('hides workflow rows when project group is collapsed', async () => {
      const user = userEvent.setup()
      const onToggleProject = vi.fn()
      const grouped = new Map([
        ['proj-1', { project: { id: 'proj-1', name: 'Project Alpha' } as never, workflows: [baseWorkflow] }],
      ])

      renderInTable(
        <GroupedWorkflowsTableBody
          groupedWorkflows={grouped}
          collapsedProjects={new Set(['proj-1'])}
          onToggleProject={onToggleProject}
          isWorkflowProjectBuiltin={isWorkflowProjectBuiltin}
          rowActionCallbacks={rowActionCallbacks}
        />
      )

      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      expect(screen.queryByText('Deploy Pipeline')).not.toBeInTheDocument()

      await user.click(screen.getByText('Project Alpha'))
      expect(onToggleProject).toHaveBeenCalledWith('proj-1')
    })
  })

  describe('FlatWorkflowsTableBody', () => {
    it('renders workflow rows', () => {
      renderInTable(
        <FlatWorkflowsTableBody
          workflows={[baseWorkflow]}
          isWorkflowProjectBuiltin={isWorkflowProjectBuiltin}
          rowActionCallbacks={rowActionCallbacks}
        />
      )

      expect(screen.getByText('Deploy Pipeline')).toBeInTheDocument()
    })

    it('scopes row can_i checks to workflow.project_id when the kebab opens', async () => {
      const user = userEvent.setup()
      renderInTable(
        <FlatWorkflowsTableBody
          workflows={[baseWorkflow]}
          isWorkflowProjectBuiltin={isWorkflowProjectBuiltin}
          rowActionCallbacks={rowActionCallbacks}
        />
      )

      expect(accessFetchClient.POST).not.toHaveBeenCalled()

      await user.click(screen.getByRole('button', { name: 'Actions for Deploy Pipeline' }))

      await waitFor(() => {
        expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
          body: { action: 'update', resource_type: 'workflow', resource_project: 'proj-1' },
        })
      })
      expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
        body: { action: 'delete', resource_type: 'workflow', resource_project: 'proj-1' },
      })
      expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
        body: { action: 'run', resource_type: 'execution', resource_project: 'proj-1' },
      })
      expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
        body: { action: 'create', resource_type: 'workflow', resource_project: 'proj-1' },
      })
    })
  })
})
