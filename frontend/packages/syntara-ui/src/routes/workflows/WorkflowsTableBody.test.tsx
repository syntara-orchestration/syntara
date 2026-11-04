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

const mockUser = { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'demo', type: 'user' as const }

const baseWorkflow: Workflow = {
  id: 'wf-1',
  name: 'Deploy Pipeline',
  current_version: 1,
  is_builtin: false,
  is_enabled: false,
  published_version_id: null,
  step_types: [],
  project_id: 'proj-1',
  created_at: '2023-01-01T12:00:00Z',
  updated_at: '2023-01-02T12:00:00Z',
  created_by: mockUser,
  updated_by: mockUser,
}

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
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })
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

    it('renders linked usernames in Created at and Updated at columns', () => {
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

      const userLinks = screen.getAllByRole('link', { name: 'demo' })
      expect(userLinks).toHaveLength(2)
      for (const link of userLinks) {
        expect(link).toHaveAttribute('href', expect.stringContaining(mockUser.id))
      }
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

    it('renders linked usernames in Created at and Updated at columns', () => {
      renderInTable(
        <FlatWorkflowsTableBody
          workflows={[baseWorkflow]}
          isWorkflowProjectBuiltin={isWorkflowProjectBuiltin}
          rowActionCallbacks={rowActionCallbacks}
        />
      )

      const userLinks = screen.getAllByRole('link', { name: 'demo' })
      expect(userLinks).toHaveLength(2)
      for (const link of userLinks) {
        expect(link).toHaveAttribute('href', expect.stringContaining(mockUser.id))
      }
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

    it('disables authoring menu actions for a blocked workflow type while preserving run, history, and export', async () => {
      const user = userEvent.setup()
      vi.mocked(accessFetchClient.POST).mockImplementation((_path, options) => {
        const body = Reflect.get(options, 'body') as {
          resource_type?: string
          resource_labels?: { kind?: string }
        }
        const allowed = body?.resource_type === 'step_type' ? body.resource_labels?.kind !== 'script' : true
        return Promise.resolve({ data: { allowed } })
      })
      const workflow: Workflow = {
        ...baseWorkflow,
        published_version_id: 'version-1',
        step_types: ['script'],
      }
      renderInTable(
        <FlatWorkflowsTableBody
          workflows={[workflow]}
          isWorkflowProjectBuiltin={isWorkflowProjectBuiltin}
          rowActionCallbacks={rowActionCallbacks}
        />
      )

      await user.click(screen.getByRole('button', { name: 'Actions for Deploy Pipeline' }))

      const editItem = await screen.findByRole('menuitem', { name: /Edit workflow/ })
      expect(editItem).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Duplicate workflow/ })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Publish workflow/ })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Unpublish workflow/ })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Delete workflow/ })).toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Run published version/ })).not.toHaveAttribute(
        'aria-disabled',
        'true'
      )
      expect(screen.getByRole('menuitem', { name: /View run history/ })).not.toHaveAttribute('aria-disabled', 'true')
      expect(screen.getByRole('menuitem', { name: /Export workflow/ })).not.toHaveAttribute('aria-disabled', 'true')
      expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
        body: {
          action: 'write',
          resource_type: 'step_type',
          resource_labels: { kind: 'script' },
          resource_project: 'proj-1',
        },
      })
    })

    it('does not fire can_i or render a kebab when showRowActions is false', () => {
      renderInTable(<FlatWorkflowsTableBody workflows={[baseWorkflow]} showRowActions={false} />)

      expect(screen.getByText('Deploy Pipeline')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Actions for Deploy Pipeline' })).not.toBeInTheDocument()
      expect(accessFetchClient.POST).not.toHaveBeenCalled()
    })
  })
})
