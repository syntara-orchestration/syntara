/** AAP-97771: deleting a workflow step must require confirmation and preserve configuration on cancel. */
import { ActivityTypeEnum, type Activity, type WorkflowWithVersion } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReactFlowProvider } from '@xyflow/react'
import type { ComponentProps, ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { approvalsClient, executionsClient, workflowClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { routerTestState } from '../../test/setup'

// Mock dependencies
vi.mock('../../client', () => ({
  workflowClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  executionsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  approvalsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../hooks/routing/useLocation', () => ({
  useLocation: () => '/workflow-builder/workflow-1',
}))

vi.mock('../../hooks/useProjectSelector', () => ({
  useProjectSelector: () => ({
    selectedProject: { id: 'project-1', name: 'Test Project' },
    stableProjectId: 'project-1',
    isAllProjects: false,
    projects: [{ id: 'project-1', name: 'Test Project' }],
    ProjectSelector: null,
  }),
}))

vi.mock('../../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({
    registerSaveHandler: vi.fn(),
    unregisterSaveHandler: vi.fn(),
  }),
}))

vi.mock('./useBuilderPermissions', () => ({
  useBuilderPermissions: () => ({
    canEdit: true,
    canCreate: true,
    canRun: true,
    canDelete: true,
    isLoading: false,
    tooltips: { edit: '', save: '', publish: '', unpublish: '', run: '', delete: '', create: '' },
  }),
}))

import { BuilderContent } from './BuilderContent'

type BuilderContentProps = ComponentProps<typeof BuilderContent>

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>
      <ReactFlowProvider>{children}</ReactFlowProvider>
    </AlertProvider>
  </QueryClientProvider>
)

async function renderBuilder(props: BuilderContentProps) {
  const view = render(<BuilderContent {...props} />, { wrapper })
  await waitFor(() => {
    expect(screen.getByPlaceholderText('Workflow name')).toBeInTheDocument()
  })
  return view
}

describe('BuilderContent - Delete Workflow', () => {
  const mockWorkflow = {
    id: 'workflow-1',
    name: 'Test Workflow',
    description: 'Test Description',
    is_enabled: true,
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-02T00:00:00Z',
    created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1', type: 'user' },
    current_version: 1,
    version: {
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'Test Workflow',
        description: 'Test Description',
        triggers: [],
        nodes: [],
        edges: [],
        $defs: {},
      },
    },
  } as unknown as WorkflowWithVersion

  const createMockMutation = (mutate = vi.fn()) => ({
    mutate,
    mutateAsync: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    context: undefined,
    failureCount: 0,
    failureReason: null,
    status: 'idle' as const,
    submittedAt: 0,
  })

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()

    vi.mocked(approvalsClient.useQuery).mockReturnValue({ data: undefined, refetch: vi.fn() })
    vi.mocked(approvalsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false })

    vi.mocked(executionsClient.useQuery).mockImplementation((method, path) => {
      if (method === 'get' && path === '/executions') {
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        }
      }
      return {
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }
    })

    vi.mocked(workflowClient.useQuery).mockImplementation((method, path) => {
      if (method === 'get' && path === '/workflows') {
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        }
      }
      return {
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }
    })

    vi.mocked(workflowClient.useMutation).mockReturnValue(createMockMutation())
    vi.mocked(executionsClient.useMutation).mockReturnValue(createMockMutation())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('shows delete button in kebab menu for existing workflows', async () => {
    const user = userEvent.setup()
    await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

    // Find and click kebab menu
    const kebabButton = screen.getByLabelText('Workflow actions')
    await user.click(kebabButton)

    // Verify delete option exists
    await waitFor(() => {
      expect(screen.getByText('Delete workflow')).toBeInTheDocument()
    })
  })

  it('does not show delete button for new workflows', async () => {
    const user = userEvent.setup()
    await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

    // Kebab menu exists (for export/import) but delete should not be available
    const kebabButton = screen.getByLabelText('Workflow actions')
    await user.click(kebabButton)

    await waitFor(() => {
      expect(screen.queryByText('Delete workflow')).not.toBeInTheDocument()
    })
  })

  it('opens delete confirmation modal when delete is clicked', async () => {
    const user = userEvent.setup()
    await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

    // Open kebab menu
    const kebabButton = screen.getByLabelText('Workflow actions')
    await user.click(kebabButton)

    // Click delete
    const deleteItem = await screen.findByText('Delete workflow')
    await user.click(deleteItem)

    // Verify modal appears
    await waitFor(() => {
      expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
      expect(
        screen.getByText(
          /will be deleted and any in-progress runs will stop immediately\. This action cannot be undone\./
        )
      ).toBeInTheDocument()
    })
  })

  it('deletes workflow and navigates to new workflow page', async () => {
    const mockDeleteMutate = vi.fn(
      (params: unknown, callbacks?: { onSuccess?: (data: unknown, variables: unknown, context: unknown) => void }) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess(undefined, params, undefined)
        }
      }
    )

    vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
      if (method === 'delete') {
        return createMockMutation(mockDeleteMutate)
      }
      return createMockMutation()
    })

    const user = userEvent.setup()
    await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

    // Open kebab and click delete
    const kebabButton = screen.getByLabelText('Workflow actions')
    await user.click(kebabButton)
    await user.click(await screen.findByText('Delete workflow'))

    // Acknowledge and confirm deletion
    await screen.findByText('Delete workflow?')
    await user.click(
      screen.getByRole('checkbox', {
        name: /I understand this workflow will be deleted and any in-progress runs will stop immediately/,
      })
    )
    await user.click(screen.getByRole('button', { name: 'Delete workflow' }))

    // Verify deletion and navigation
    await waitFor(() => {
      expect(mockDeleteMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          params: { path: { workflow_id: 'workflow-1' } },
        }),
        expect.any(Object)
      )
      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
      expect(screen.getByText('Workflow deleted')).toBeInTheDocument()
    })
  })

  it('handles delete error and shows error alert', async () => {
    const user = userEvent.setup()
    const mockError = { message: 'Cannot delete workflow with active executions' }
    const mockDeleteMutate = vi.fn(
      (params: unknown, callbacks?: { onError?: (error: unknown, variables: unknown, context: unknown) => void }) => {
        if (callbacks?.onError) {
          callbacks.onError(mockError, params, undefined)
        }
      }
    )

    vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
      if (method === 'delete') {
        return createMockMutation(mockDeleteMutate)
      }
      return createMockMutation()
    })

    await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

    // Open kebab and click delete
    await user.click(screen.getByLabelText('Workflow actions'))
    await user.click(await screen.findByText('Delete workflow'))

    // Acknowledge and confirm deletion
    await screen.findByText('Delete workflow?')
    await user.click(
      screen.getByRole('checkbox', {
        name: /I understand this workflow will be deleted and any in-progress runs will stop immediately/,
      })
    )
    await user.click(screen.getByRole('button', { name: 'Delete workflow' }))

    // Verify error alert
    await waitFor(() => {
      expect(mockDeleteMutate).toHaveBeenCalled()
      expect(screen.getByText('Failed to delete workflow')).toBeInTheDocument()
      expect(screen.getByText(/Failed to delete workflow ".+":/)).toBeInTheDocument()
    })
  })

  it('can cancel delete operation', async () => {
    const user = userEvent.setup()
    await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

    // Open kebab and click delete
    await user.click(screen.getByLabelText('Workflow actions'))
    await user.click(await screen.findByText('Delete workflow'))

    // Modal appears, then cancel
    await screen.findByText('Delete workflow?')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    // Modal closes
    await waitFor(() => {
      expect(screen.queryByText('Delete workflow?')).not.toBeInTheDocument()
    })
  })

  it('preserves a configured workflow step when its delete confirmation is cancelled', async () => {
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(300)
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(120)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 300, 120))
    vi.stubGlobal(
      'DOMMatrixReadOnly',
      class {
        readonly m22 = 1
      }
    )
    vi.stubGlobal(
      'ResizeObserver',
      class {
        readonly callback: ResizeObserverCallback
        constructor(callback: ResizeObserverCallback) {
          this.callback = callback
        }
        observe(target: Element) {
          setTimeout(
            () => this.callback([{ target, contentRect: new DOMRect(0, 0, 300, 120) } as ResizeObserverEntry], this),
            0
          )
        }
        unobserve = vi.fn()
        disconnect = vi.fn()
      }
    )
    const user = userEvent.setup()
    const activity = {
      id: 'script-1',
      name: 'Configured script',
      type: ActivityTypeEnum.SCRIPT,
      parameters: { language: 'python', code: 'print("keep this configuration")' },
    } satisfies Activity
    const version = mockWorkflow.version
    if (!version) throw new Error('Expected a versioned test workflow')
    const workflow: WorkflowWithVersion = {
      ...mockWorkflow,
      version: {
        ...version,
        workflow_definition: {
          ...version.workflow_definition,
          nodes: [activity],
        },
      },
    }

    await renderBuilder({ workflow, isNew: false, workflowId: 'workflow-1' })
    const stepMenu = await screen.findByRole('button', { name: 'Step actions menu' })
    expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toEqual([activity])

    await user.click(stepMenu)
    await user.click(await screen.findByRole('menuitem', { name: 'Delete' }))

    expect.soft(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toEqual([activity])
    const confirmationDialog = await screen.findByRole('dialog')
    await user.click(within(confirmationDialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText(activity.name)).toBeInTheDocument()
    expect(useWorkflowStore.getState().currentWorkflow?.workflow.activities).toEqual([activity])
  })
})
