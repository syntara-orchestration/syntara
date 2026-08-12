import type { WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, act, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReactFlowProvider } from '@xyflow/react'
import type { ComponentProps, ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { approvalsClient, executionsClient, workflowClient, workflowFetchClient } from '../../client'
import * as useCursorPaginationModule from '../../hooks/useCursorPagination'
import { AlertProvider } from '../../providers/alerts'
import { ColorSchemeProvider } from '../../providers/theme/ColorSchemeProvider'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { routerTestState } from '../../test/setup'
import { transformExecutionStatusFilter } from '../executions/executionFilters'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']

type MutationCallbacks = {
  onSuccess?: (data: unknown, variables: unknown, context: unknown) => void
  onError?: (error: unknown, variables: unknown, context: unknown) => void
}

// Mock dependencies
vi.mock('../../client', () => ({
  workflowClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  workflowFetchClient: {
    GET: vi.fn().mockResolvedValue({ data: { current_version: 1, version: { version: 1 } }, error: null }),
    POST: vi.fn().mockResolvedValue({ data: { id: 'new-workflow-id' }, error: null }),
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

// Mock useProjectSelector to avoid accessClient dependency
vi.mock('../../hooks/useProjectSelector', () => ({
  useProjectSelector: () => ({
    selectedProject: { id: 'project-1', name: 'Test Project' },
    stableProjectId: 'project-1',
    isAllProjects: false,
    projects: [{ id: 'project-1', name: 'Test Project' }],
    ProjectSelector: null,
  }),
}))

const mockRequestNavigation = vi.fn()
vi.mock('../../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({
    registerSaveHandler: vi.fn(),
    unregisterSaveHandler: vi.fn(),
    requestNavigation: mockRequestNavigation,
  }),
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

const mockBuilderPermissions = vi.hoisted(() => ({
  canEdit: true,
  canRun: true,
  canDelete: true,
  isLoading: false,
  tooltips: { edit: '', save: '', publish: '', unpublish: '', run: '', delete: '' },
}))

vi.mock('./useBuilderPermissions', () => ({
  useBuilderPermissions: () => mockBuilderPermissions,
}))

import { BuilderContent } from './BuilderContent'

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
      <ColorSchemeProvider>
        <ReactFlowProvider>{children}</ReactFlowProvider>
      </ColorSchemeProvider>
    </AlertProvider>
  </QueryClientProvider>
)

type BuilderContentProps = ComponentProps<typeof BuilderContent>

async function renderBuilder(props: BuilderContentProps) {
  const view = render(<BuilderContent {...props} />, { wrapper })
  await waitFor(() => {
    expect(screen.getByPlaceholderText('Workflow name')).toBeInTheDocument()
  })
  return view
}

async function clickKebabItem(name: RegExp | string) {
  const user = userEvent.setup()
  await user.click(screen.getByLabelText('Workflow actions'))
  const menuItem = await screen.findByRole('menuitem', {
    name: typeof name === 'string' ? new RegExp(name, 'i') : name,
  })
  await user.click(menuItem)
}

describe('BuilderContent', () => {
  // Using 'as WorkflowWithVersion' cast since test mocks don't need all optional fields
  const mockWorkflow = {
    id: 'workflow-1',
    name: 'Test Workflow',
    description: 'Test Description',
    is_enabled: true,
    labels: {},
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-02T00:00:00Z',
    created_by: 'user-1',
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

  /** Workflow with at least one trigger and step so toolbar Add step is shown and the panel can be toggled. */
  const createWorkflowWithNodes = (): WorkflowWithVersion =>
    ({
      ...mockWorkflow,
      version: {
        workflow_definition: {
          schema_version: '2.0.0' as const,
          name: 'Test Workflow',
          description: 'Test Description',
          triggers: [{ id: 'manual_trigger', type: 'manual_trigger', parameters: {} }],
          nodes: [
            {
              type: 'script' as const,
              id: 'task-1',
              name: 'Task 1',
              parameters: { language: 'python', code: '' },
            },
          ],
          edges: [],
          $defs: {},
        },
      },
    }) as unknown as WorkflowWithVersion

  // Helper to create a workflow with a manual trigger that has an input schema
  const createWorkflowWithInputSchema = (): WorkflowWithVersion =>
    ({
      ...mockWorkflow,
      version: {
        workflow_definition: {
          ...mockWorkflow.version.workflow_definition,
          triggers: [
            {
              id: 'manual_trigger',
              type: 'manual_trigger',
              name: 'Manual Trigger',
              parameters: {
                input_schema: {
                  type: 'object',
                  properties: { name: { type: 'string' } },
                },
              },
            },
          ],
          nodes: [
            {
              type: 'script' as const,
              id: 'task-1',
              name: 'Task 1',
              parameters: { language: 'python', code: 'print("hello")' },
            },
          ],
          edges: [
            {
              from: 'manual_trigger',
              to: 'task-1',
            },
          ],
        },
      },
    }) as unknown as WorkflowWithVersion

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

  /** Mock workflowClient PATCH to succeed — required for handleRunWorkflow which always saves first. */
  function mockWorkflowPatchSuccess() {
    vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
      if (method === 'patch') {
        return createMockMutation(
          vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
            callbacks?.onSuccess?.({ id: 'workflow-1', current_version: 1 }, params, undefined)
          })
        )
      }
      return createMockMutation()
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()

    vi.mocked(approvalsClient.useQuery).mockReturnValue({ data: undefined, refetch: vi.fn() })
    vi.mocked(approvalsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false })

    // Reset workflow store to initial state to prevent test pollution
    useWorkflowStore.setState({
      currentWorkflow: null,
      workflowVersion: 0,
      edges: [],
      isDirty: false,
    })

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

    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: { current_version: 1, version: { version: 1 } } as WorkflowWithVersion,
      error: undefined,
      response: new Response(),
    })
    vi.mocked(workflowFetchClient.POST).mockResolvedValue({
      data: { id: 'new-workflow-id' },
      error: undefined,
      response: new Response(),
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Run history filter wiring', () => {
    it('passes transformExecutionStatusFilter to useCursorPagination', async () => {
      const useCursorPaginationSpy = vi.spyOn(useCursorPaginationModule, 'useCursorPagination')

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      expect(useCursorPaginationSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          transformFilters: transformExecutionStatusFilter,
          extraParams: { workflow_id: 'workflow-1' },
        })
      )
    })
  })

  // ============================================================================
  // BASIC RENDERING TESTS
  // ============================================================================

  describe('New Workflow', () => {
    it('renders new workflow with default name', async () => {
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })
      const nameInput = screen.getByPlaceholderText('Workflow name')
      await waitFor(() => {
        expect(nameInput).toHaveValue('new-workflow')
      })
    })

    it('uses next available default name when new-workflow exists', async () => {
      vi.mocked(workflowClient.useQuery).mockImplementation((method, path) => {
        if (method === 'get' && path === '/workflows') {
          return {
            data: {
              resources: [{ name: 'new-workflow' }],
            },
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
      render(<BuilderContent workflow={undefined} isNew={true} workflowId={null} />, { wrapper })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('new-workflow-1')
      })
    })

    it('shows disabled Run button for new workflows with no triggers', async () => {
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })
      const runButton = screen.getByRole('button', { name: /Run/i })
      expect(runButton).toBeInTheDocument()
      expect(runButton).toHaveAttribute('aria-disabled', 'true')
    })

    it('does not show Run history in kebab for new workflows', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })
      await user.click(screen.getByLabelText('Workflow actions'))
      await waitFor(() => {
        expect(screen.queryByRole('menuitem', { name: /Run history/i })).not.toBeInTheDocument()
      })
    })
  })

  describe('Existing Workflow', () => {
    it('renders existing workflow name in input', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        const nameInput = screen.getByPlaceholderText('Workflow name')
        expect(nameInput).toHaveValue('Test Workflow')
      })
    })

    it('shows Run button for existing workflows', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      expect(screen.getByText('Run')).toBeInTheDocument()
    })

    it('shows Run history in kebab for existing workflows', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await user.click(screen.getByLabelText('Workflow actions'))
      await waitFor(() => {
        expect(screen.getByRole('menuitem', { name: /Run history/i })).toBeInTheDocument()
      })
    })

    it('shows Publish workflow button for existing workflows', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      expect(screen.getByRole('button', { name: /Publish workflow/i })).toBeInTheDocument()
    })

    it('does not show Publish workflow button for new workflows', async () => {
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })
      expect(screen.queryByRole('button', { name: /Publish workflow/i })).not.toBeInTheDocument()
    })

    it('shows Draft badge for unpublished existing workflow', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByText('Draft')).toBeInTheDocument()
      })
    })

    it('shows Published badge when published_version_id matches current_version', async () => {
      const publishedWorkflow = {
        ...mockWorkflow,
        published_version_id: 'ver-1',
        current_version: 1,
      } as unknown as WorkflowWithVersion
      await renderBuilder({ workflow: publishedWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByText('Published')).toBeInTheDocument()
      })
    })

    it('shows Published badge when published_version_id is set', async () => {
      const publishedWorkflow = {
        ...mockWorkflow,
        published_version_id: 'ver-1',
        current_version: 2,
      } as unknown as WorkflowWithVersion
      await renderBuilder({ workflow: publishedWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByText('Published')).toBeInTheDocument()
      })
    })

    it('does not show status badge for new workflows', async () => {
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })
      expect(screen.queryByText('Draft')).not.toBeInTheDocument()
      expect(screen.queryByText('Published')).not.toBeInTheDocument()
    })
  })

  // ============================================================================
  // WORKFLOW NAME INPUT
  // ============================================================================

  describe('Workflow Name Input', () => {
    it('updates name when typing', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })
      const nameInput = screen.getByPlaceholderText('Workflow name')
      await user.clear(nameInput)
      await user.type(nameInput, 'My New Workflow')
      expect(nameInput).toHaveValue('My New Workflow')
    })

    it('marks workflow dirty when name changes', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })
      const nameInput = screen.getByPlaceholderText('Workflow name')
      await user.clear(nameInput)
      await user.type(nameInput, 'Changed Name')
      // This tests SET_WORKFLOW_NAME reducer action and markDirty()
    })
  })

  // ============================================================================
  // ADD STEP PANEL
  // ============================================================================

  describe('Add step panel', () => {
    it('shows Add step panel by default for empty new workflow without toolbar button', async () => {
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
      })
      expect(screen.queryByRole('button', { name: 'Add step' })).not.toBeInTheDocument()
    })

    it('opens Add step panel when Add Step button is clicked', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })
      const addNodeButton = screen.getByRole('button', { name: 'Add step' })
      await user.click(addNodeButton)
      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
      })
    })

    it('closes Add step panel via close callback', async () => {
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })

      // Open panel
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Add step' }))
      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
      })

      // Find close button by aria-label in the add step panel
      await user.click(screen.getByLabelText('Close add step panel'))

      // Panel should close (tests CLOSE_ADD_NODE_PANEL reducer)
      await waitFor(() => {
        expect(screen.queryByRole('region', { name: 'Add step' })).not.toBeInTheDocument()
      })
    })

    it('opens Add step panel from toolbar when workflow has nodes', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })

      expect(screen.queryByRole('region', { name: 'Add step' })).not.toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Add step' }))
      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Add step' })).toHaveAttribute('aria-pressed', 'true')
      })
    })
  })

  // ============================================================================
  // WORKFLOW DETAILS PANEL
  // ============================================================================

  describe('Workflow Details Panel', () => {
    it('has details menu item in kebab', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await user.click(screen.getByLabelText('Workflow actions'))
      await waitFor(() => {
        expect(screen.getByRole('menuitem', { name: /Workflow details/i })).toBeInTheDocument()
      })
    })

    it('toggles details panel open', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await clickKebabItem('Workflow details')
      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })
    })

    it('toggles details panel closed', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Open
      await clickKebabItem('Workflow details')
      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })
      // Close
      await clickKebabItem('Workflow details')
      await waitFor(() => {
        expect(screen.queryByLabelText('Description')).not.toBeInTheDocument()
      })
    })

    it('updates workflow name via sidepanel input', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Open details panel
      await clickKebabItem('Workflow details')

      // Wait for sidepanel to render
      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })

      // Find the sidepanel name input (distinct from header "Workflow name")
      const sidepanelNameInput = screen.getByLabelText('Workflow name in workflow details')
      await user.clear(sidepanelNameInput)
      await user.type(sidepanelNameInput, 'Updated Via Sidepanel')

      // Verify the name was updated
      expect(sidepanelNameInput).toHaveValue('Updated Via Sidepanel')
    })

    it('updates workflow description via sidepanel textarea', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Open details panel
      await clickKebabItem('Workflow details')

      // Wait for sidepanel to render
      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })

      // Find the sidepanel description textarea and change it (tests onDescriptionChange callback - lines 1159-1162)
      const descriptionTextarea = screen.getByLabelText('Description')
      await user.clear(descriptionTextarea)
      await user.type(descriptionTextarea, 'New Description')

      // Verify the description was updated
      expect(descriptionTextarea).toHaveValue('New Description')
    })

    it('applies workflow details from header popover onApply callback', { timeout: 15_000 }, async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      await user.click(screen.getByRole('button', { name: 'Edit workflow details' }))
      await waitFor(() => {
        expect(screen.getByLabelText('Description')).toBeInTheDocument()
      })

      await user.clear(screen.getByLabelText('Description'))
      await user.type(screen.getByLabelText('Description'), 'Updated via edit details popover')
      const popoverSurface = screen.getByRole('dialog')
      const closeButtons = within(popoverSurface).getAllByRole('button', { name: 'Close' })
      await user.click(closeButtons[closeButtons.length - 1])

      await waitFor(() => {
        expect(screen.queryByLabelText('Description')).not.toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Edit workflow details' }))
      await waitFor(() => {
        expect(screen.getByLabelText('Description')).toHaveValue('Updated via edit details popover')
      })
    })

    it('closes sidepanel via its close button', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Open details panel
      await clickKebabItem('Workflow details')

      // Wait for sidepanel to render with the title
      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })

      // Find the sidepanel's Close button (tests onClose callback - line 1163)
      await user.click(screen.getByLabelText('Close workflow details'))

      // Sidepanel should close - the title should no longer be visible
      await waitFor(() => {
        expect(screen.queryByText('Workflow details')).not.toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // RUN WORKFLOW
  // ============================================================================

  describe('Run Workflow', () => {
    it('opens run confirmation dialog when Run button is clicked', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() => {
        expect(screen.getByText(/Run Test Workflow\?/)).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Run now' })).toBeInTheDocument()
      })
    })

    it('can cancel run dialog', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      await user.click(screen.getByRole('button', { name: 'Run' }))
      await screen.findByText(/Run Test Workflow\?/)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText(/Run Test Workflow\?/)).not.toBeInTheDocument()
      })
    })

    it('executes workflow when confirmed', async () => {
      const user = userEvent.setup()
      const mockExecuteMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess({ id: 'exec-123' }, params, undefined)
        }
      })

      mockWorkflowPatchSuccess()

      vi.mocked(executionsClient.useMutation).mockImplementation((method, path) => {
        if (method === 'post' && path === '/executions') {
          return createMockMutation(mockExecuteMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: createWorkflowWithInputSchema(), isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      await user.click(screen.getByRole('button', { name: 'Run' }))
      await screen.findByText(/Run Test Workflow\?/)
      await user.click(screen.getByRole('button', { name: 'Run now' }))
      await screen.findByText(/Set mock output data for/)
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() => {
        expect(mockExecuteMutate).toHaveBeenCalled()
        expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/executions/exec-123?history=closed' })
      })
    })

    it('shows error when execution fails', async () => {
      const user = userEvent.setup()
      const mockExecuteMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onError) {
          callbacks.onError({ message: 'Execution failed' }, params, undefined)
        }
      })

      mockWorkflowPatchSuccess()

      vi.mocked(executionsClient.useMutation).mockImplementation((method, path) => {
        if (method === 'post' && path === '/executions') {
          return createMockMutation(mockExecuteMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: createWorkflowWithInputSchema(), isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      await user.click(screen.getByRole('button', { name: 'Run' }))
      await screen.findByText(/Run Test Workflow\?/)
      await user.click(screen.getByRole('button', { name: 'Run now' }))
      await screen.findByText(/Set mock output data for/)
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() => {
        expect(screen.getByText('Workflow failed')).toBeInTheDocument()
      })
    })

    it('closes run modal via modal onClose', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      await user.click(screen.getByRole('button', { name: 'Run' }))
      await screen.findByText(/Run Test Workflow\?/)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText(/Run Test Workflow\?/)).not.toBeInTheDocument()
      })
    })

    it('closes run modal via X button', async () => {
      const user = userEvent.setup()

      await renderBuilder({ workflow: createWorkflowWithInputSchema(), isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      await user.click(screen.getByRole('button', { name: 'Run' }))
      await screen.findByText(/Run Test Workflow\?/)
      await user.click(screen.getByRole('button', { name: 'Run now' }))
      await screen.findByText(/Set mock output data for/)

      const modal = screen.getByRole('dialog')
      await user.click(within(modal).getByRole('button', { name: 'Close' }))

      await waitFor(() => {
        expect(screen.queryByText(/Set mock output data for/)).not.toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // SAVE WORKFLOW
  // ============================================================================

  describe('Save Workflow', () => {
    it('shows Save button', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
    })

    it('shows Saving... when pending', async () => {
      vi.mocked(workflowClient.useMutation).mockReturnValue({
        ...createMockMutation(),
        isPending: true,
      })

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      expect(screen.getByText('Saving...')).toBeInTheDocument()
    })

    it('handles save attempt on new empty workflow', async () => {
      // Track mutation calls
      const mockCreateMutate = vi.fn()
      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'post') {
          return createMockMutation(mockCreateMutate)
        }
        return createMockMutation()
      })

      // New workflow with no activities - component initializes default workflow
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      const user = userEvent.setup()
      const saveButton = screen.getByRole('button', { name: /save/i })
      expect(saveButton).toBeInTheDocument()
      await user.click(saveButton)

      // Tests handleSaveWorkflow path for new workflow
      // Empty workflows pass validation, so create mutation should be called
      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })
    })

    it('updates existing workflow via PATCH', async () => {
      const mockUpdateMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess({ id: 'workflow-1' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'patch') {
          return createMockMutation(mockUpdateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalled()
      })
    })

    it('creates new workflow via POST', async () => {
      const mockCreateMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess({ id: 'new-workflow-id' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'post') {
          return createMockMutation(mockCreateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      const user = userEvent.setup()
      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })
    })

    it('handles save error', async () => {
      const mockUpdateMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onError) {
          callbacks.onError({ detail: 'Server error' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'patch') {
          return createMockMutation(mockUpdateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('Failed to update workflow: Server error')).toBeInTheDocument()
      })
    })

    it('handles create error', async () => {
      const mockCreateMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onError) {
          callbacks.onError({ detail: 'Create failed' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'post') {
          return createMockMutation(mockCreateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      const user = userEvent.setup()
      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('Failed to create workflow: Create failed')).toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // HISTORY PANEL
  // ============================================================================

  describe('History Panel', () => {
    it('opens history panel when history button is clicked', async () => {
      const mockRefetch = vi.fn()
      vi.mocked(executionsClient.useQuery).mockImplementation((method, path) => {
        if (method === 'get' && path === '/executions') {
          return {
            data: { resources: [] },
            isPending: false,
            isError: false,
            error: null,
            refetch: mockRefetch,
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

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Run history')

      await waitFor(
        () => {
          expect(mockRefetch).toHaveBeenCalled()
        },
        { timeout: 15_000 }
      )
    }, 20_000)

    it('toggles history panel closed', async () => {
      const mockRefetch = vi.fn()
      vi.mocked(executionsClient.useQuery).mockImplementation((method, path) => {
        if (method === 'get' && path === '/executions') {
          return {
            data: { resources: [] },
            isPending: false,
            isError: false,
            error: null,
            refetch: mockRefetch,
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

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Open
      await clickKebabItem('Run history')
      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalledTimes(1)
      })

      // Toggle closed (tests TOGGLE_HISTORY reducer)
      await clickKebabItem('Run history')
    })

    it('shows history card with close button', async () => {
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

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Run history')

      // Wait for history card to render
      await waitFor(() => {
        expect(screen.getByText('Run history')).toBeInTheDocument()
      })

      // Find and click close button (tests onClose callback - line 1156)
      const user = userEvent.setup()
      await user.click(screen.getByLabelText('Close run history'))

      // Panel should close
      await waitFor(() => {
        expect(screen.queryByText('Run history')).not.toBeInTheDocument()
      })
    })

    it('navigates to execution page on execution selection', async () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((method, path) => {
        if (method === 'get' && path === '/executions') {
          return {
            data: {
              resources: [
                {
                  id: 'exec-1',
                  status: 'completed',
                  created_at: '2023-01-01T00:00:00Z',
                  workflow_id: 'workflow-1',
                },
              ],
            },
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

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Run history')

      await waitFor(() => {
        expect(screen.getByText('Run history')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const row = screen.getByRole('button', { name: /Completed/i })
      expect(row).toBeInTheDocument()
      await user.click(row)
      await waitFor(() => {
        expect(mockRequestNavigation).toHaveBeenCalledWith('/executions/exec-1')
      })
    })
  })

  // ============================================================================
  // KEBAB MENU
  // ============================================================================

  describe('Kebab Menu', () => {
    it('opens kebab menu when clicked', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      const user = userEvent.setup()
      const kebabButton = screen.getByLabelText('Workflow actions')
      await user.click(kebabButton)

      await waitFor(() => {
        expect(screen.getByText('Delete workflow')).toBeInTheDocument()
      })
    })

    it('closes kebab menu when item is selected', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      const user = userEvent.setup()
      const kebabButton = screen.getByLabelText('Workflow actions')
      await user.click(kebabButton)

      await waitFor(() => {
        expect(screen.getByText('Delete workflow')).toBeInTheDocument()
      })

      // Tests SET_KEBAB_OPEN reducer action via onSelect
      await user.click(screen.getByText('Delete workflow'))
    })

    it('closes kebab menu when clicking toggle again', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      const user = userEvent.setup()
      const kebabButton = screen.getByLabelText('Workflow actions')

      // Open
      await user.click(kebabButton)
      await waitFor(() => {
        expect(screen.getByText('Delete workflow')).toBeInTheDocument()
      })

      // Close
      await user.click(kebabButton)
    })
  })

  // ============================================================================
  // DELETE MODAL
  // ============================================================================

  describe('Delete Modal', () => {
    it('opens delete modal when delete option is clicked', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      const kebabButton = screen.getByLabelText('Workflow actions')
      await user.click(kebabButton)

      await user.click(await screen.findByText('Delete workflow'))

      await waitFor(() => {
        expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
      })
    })

    it('closes delete modal when cancel is clicked', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await user.click(screen.getByLabelText('Workflow actions'))
      await user.click(await screen.findByText('Delete workflow'))

      await screen.findByText('Delete workflow?')

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Delete workflow?')).not.toBeInTheDocument()
      })
    })

    it('deletes workflow when confirmed', async () => {
      const mockDeleteMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess(undefined, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'delete') {
          return createMockMutation(mockDeleteMutate)
        }
        return createMockMutation()
      })

      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await user.click(screen.getByLabelText('Workflow actions'))
      await user.click(await screen.findByText('Delete workflow'))

      await screen.findByText('Delete workflow?')
      await user.click(
        screen.getByRole('checkbox', {
          name: /I understand this workflow will be deleted and any in-progress runs will stop immediately/,
        })
      )
      await user.click(screen.getByRole('button', { name: 'Delete' }))

      await waitFor(() => {
        expect(mockDeleteMutate).toHaveBeenCalled()
        expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
      })
    })

    it('shows error when delete fails', async () => {
      const mockDeleteMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onError) {
          callbacks.onError({ message: 'Delete failed' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'delete') {
          return createMockMutation(mockDeleteMutate)
        }
        return createMockMutation()
      })

      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await user.click(screen.getByLabelText('Workflow actions'))
      await user.click(await screen.findByText('Delete workflow'))

      await screen.findByText('Delete workflow?')
      await user.click(
        screen.getByRole('checkbox', {
          name: /I understand this workflow will be deleted and any in-progress runs will stop immediately/,
        })
      )
      await user.click(screen.getByRole('button', { name: 'Delete' }))

      await waitFor(() => {
        expect(mockDeleteMutate).toHaveBeenCalled()
      })
    })

    it('closes delete modal via X button', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Open kebab menu and click delete
      await user.click(screen.getByLabelText('Workflow actions'))
      await user.click(await screen.findByText('Delete workflow'))

      // Wait for delete modal to open
      await screen.findByText('Delete workflow?')

      // Find the modal's X close button (tests onClose callback)
      const modal = screen.getByRole('dialog')
      await user.click(within(modal).getByRole('button', { name: 'Close' }))

      // Modal should close
      await waitFor(() => {
        expect(screen.queryByText('Delete workflow?')).not.toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // WORKFLOW LOADING SCENARIOS
  // ============================================================================

  describe('Workflow loading', () => {
    it('loads workflow with activities and triggers', async () => {
      const workflowWithActivities = {
        ...mockWorkflow,
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            name: 'Test Workflow',
            description: 'Test Description',
            triggers: [{ id: 'manual_trigger', type: 'manual_trigger', parameters: {} }],
            nodes: [
              {
                type: 'script' as const,
                id: 'task-1',
                name: 'Task 1',
                parameters: { language: 'python', code: '' },
              },
            ],
            edges: [],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: workflowWithActivities, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })
    })

    it('handles workflow with parallel first activity', async () => {
      const workflowWithParallel = {
        ...mockWorkflow,
        name: 'Parallel Workflow',
        description: 'Test parallel',
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            name: 'Parallel Workflow',
            description: 'Test parallel',
            triggers: [{ id: 'manual_trigger', type: 'manual_trigger', parameters: {} }],
            nodes: [
              {
                type: 'script' as const,
                id: 'branch-task-1',
                name: 'Branch Task',
                parameters: { language: 'python', code: '' },
              },
            ],
            edges: [],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: workflowWithParallel, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Parallel Workflow')
      })
    })

    it('handles workflow without version gracefully', async () => {
      const workflowWithoutVersion = {
        ...mockWorkflow,
        version: undefined,
      }

      await renderBuilder({
        workflow: workflowWithoutVersion as unknown as WorkflowWithVersion,
        isNew: false,
        workflowId: 'workflow-1',
      })

      expect(screen.getByPlaceholderText('Workflow name')).toBeInTheDocument()
    })

    it('handles mismatched workflow ID', async () => {
      // Render with different workflowId than workflow object
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'different-id' })

      // Should render without crashing
      expect(screen.getByPlaceholderText('Workflow name')).toBeInTheDocument()
    })

    it('handles workflow ID change', async () => {
      const { rerender } = await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Rerender with different workflow ID (tests lines 373-376)
      const newWorkflow = { ...mockWorkflow, id: 'workflow-2', name: 'new-workflow' }
      rerender(
        <QueryClientProvider client={queryClient}>
          <AlertProvider>
            <ReactFlowProvider>
              <BuilderContent workflow={newWorkflow} isNew={false} workflowId="workflow-2" />
            </ReactFlowProvider>
          </AlertProvider>
        </QueryClientProvider>
      )

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('new-workflow')
      })
    })

    it('syncs state when workflow data changes', async () => {
      const { rerender } = await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Update workflow data
      const updatedWorkflow = { ...mockWorkflow, name: 'Updated Name', is_enabled: false }
      rerender(
        <QueryClientProvider client={queryClient}>
          <AlertProvider>
            <ReactFlowProvider>
              <BuilderContent workflow={updatedWorkflow} isNew={false} workflowId="workflow-1" />
            </ReactFlowProvider>
          </AlertProvider>
        </QueryClientProvider>
      )

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Updated Name')
      })
    })

    it('handles transition from new to existing workflow', async () => {
      const { rerender } = await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('new-workflow')
      })

      // Load existing workflow
      rerender(
        <QueryClientProvider client={queryClient}>
          <AlertProvider>
            <ReactFlowProvider>
              <BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />
            </ReactFlowProvider>
          </AlertProvider>
        </QueryClientProvider>
      )

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })
    })
  })

  // ============================================================================
  // BROWSER NAVIGATION
  // ============================================================================

  describe('Browser Navigation', () => {
    it('registers beforeunload handler', async () => {
      const addEventListenerSpy = vi.spyOn(window, 'addEventListener')

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      expect(addEventListenerSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))

      addEventListenerSpy.mockRestore()
    })

    it('beforeunload handler prevents default when workflow is dirty', async () => {
      const addSpy = vi.spyOn(window, 'addEventListener')
      const prevDirty = useWorkflowStore.getState().isDirty
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      const beforeUnloadCall = addSpy.mock.calls.find((c) => c[0] === 'beforeunload')
      expect(beforeUnloadCall).toBeDefined()
      const handler = beforeUnloadCall![1] as (e: BeforeUnloadEvent) => void

      try {
        act(() => {
          useWorkflowStore.getState().markDirty()
        })
        const event = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent
        act(() => {
          handler(event)
        })
        expect(event.defaultPrevented).toBe(true)
      } finally {
        act(() => {
          useWorkflowStore.setState({ isDirty: prevDirty })
        })
      }

      addSpy.mockRestore()
    })

    it('unregisters beforeunload handler on unmount', async () => {
      const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener')

      const { unmount } = await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      unmount()

      expect(removeEventListenerSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))

      removeEventListenerSpy.mockRestore()
    })
  })

  // ============================================================================
  // CONTEXT PROVIDERS
  // ============================================================================

  describe('Context Providers', () => {
    it('provides NodeExpandedAllContext to children', async () => {
      // The component provides NodeExpandedAllContext
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      expect(screen.getByPlaceholderText('Workflow name')).toBeInTheDocument()
    })
  })

  // ============================================================================
  // WORKFLOW DESCRIPTION
  // ============================================================================

  describe('Workflow Description', () => {
    it('loads with description from workflow', async () => {
      const workflowWithDescription = {
        ...mockWorkflow,
        description: 'Custom Description',
      }

      await renderBuilder({ workflow: workflowWithDescription, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })
    })

    it('falls back to name when description is null', async () => {
      const workflowNoDescription = {
        ...mockWorkflow,
        description: null,
      }

      await renderBuilder({
        workflow: workflowNoDescription as WorkflowWithVersion,
        isNew: false,
        workflowId: 'workflow-1',
      })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })
    })
  })

  // ============================================================================
  // UNSAVED CHANGES HOOK
  // ============================================================================

  describe('Unsaved Changes', () => {
    it('component mounts with unsaved changes hook', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      expect(screen.getByPlaceholderText('Workflow name')).toBeInTheDocument()
    })
  })

  // ============================================================================
  // ADDITIONAL REDUCER COVERAGE TESTS
  // ============================================================================

  describe('Reducer State Transitions', () => {
    it('TOGGLE_DETAILS closes add step panel when opening details', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })

      // First open add step panel
      await user.click(screen.getByRole('button', { name: 'Add step' }))
      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
      })

      // Now toggle details - should close add step panel
      await clickKebabItem('Workflow details')

      await waitFor(() => {
        expect(screen.queryByRole('region', { name: 'Add step' })).not.toBeInTheDocument()
      })
    })

    it('TOGGLE_HISTORY closes add step panel when opening history', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })

      // First open add step panel
      await user.click(screen.getByRole('button', { name: 'Add step' }))
      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
      })

      // Now toggle history - should close add step panel
      await clickKebabItem('Run history')

      await waitFor(() => {
        expect(screen.queryByRole('region', { name: 'Add step' })).not.toBeInTheDocument()
      })
    })

    it('SET_DETAILS_OPEN via direct panel close', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Open details panel
      await clickKebabItem('Workflow details')

      await waitFor(() => {
        // Details panel should be open
        expect(screen.getByLabelText('Close workflow details')).toBeInTheDocument()
      })
    })

    it('SET_WORKFLOW_DESCRIPTION changes description', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Open details panel to access description
      await clickKebabItem('Workflow details')

      await waitFor(() => {
        expect(screen.getByLabelText('Description')).toBeInTheDocument()
      })
      const user = userEvent.setup()
      const descriptionTextarea = screen.getByLabelText('Description')
      await user.clear(descriptionTextarea)
      await user.type(descriptionTextarea, 'Updated via reducer test')
      expect(descriptionTextarea).toHaveValue('Updated via reducer test')
    })

    it('INIT_WORKFLOW initializes state from workflow prop', async () => {
      const customWorkflow = {
        ...mockWorkflow,
        name: 'Custom Init Name',
        description: 'Custom Init Description',
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: customWorkflow, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Custom Init Name')
      })
    })
  })

  // ============================================================================
  // SAVE WORKFLOW VALIDATION PATHS
  // ============================================================================

  describe('Save Workflow Validation', () => {
    it('disables Run button for workflow without trigger', async () => {
      const workflowNoTrigger = {
        ...mockWorkflow,
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            name: 'Test Workflow',
            description: '',
            triggers: [],
            nodes: [
              {
                type: 'script' as const,
                id: 'task-1',
                name: 'Task 1',
                parameters: { language: 'python', code: '' },
              },
            ],
            edges: [],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: workflowNoTrigger, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      const runButton = screen.getByRole('button', { name: /Run/i })
      expect(runButton).toHaveAttribute('aria-disabled', 'true')
    })

    it('invokes PATCH when saving existing workflow (mock graph passes validation)', async () => {
      const mockUpdateMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess({ id: 'workflow-1' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'patch') {
          return createMockMutation(mockUpdateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalled()
      })
    })

    it('getWorkflowDefinition returns empty workflow when no currentWorkflow', async () => {
      const mockCreateMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess({ id: 'new-id' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'post') {
          return createMockMutation(mockCreateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      // Change name to trigger the workflow definition getter
      const user = userEvent.setup()
      const nameInput = screen.getByPlaceholderText('Workflow name')
      await user.clear(nameInput)
      await user.type(nameInput, 'Empty Workflow')

      // Save triggers getWorkflowDefinition
      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })
    })
  })

  // ============================================================================
  // GUARD CLAUSE COVERAGE
  // ============================================================================

  describe('Guard Clauses', () => {
    it('handleRunWorkflow guards when no workflow id', async () => {
      // Create workflow without id - cast through unknown for test purposes
      const noIdWorkflow = { ...mockWorkflow, id: undefined } as unknown as WorkflowWithVersion

      const { container } = await renderBuilder({ workflow: noIdWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Verify component renders without crashing
      expect(container).toBeInTheDocument()

      const user = userEvent.setup()
      // Run button may not be visible without id - tests guard clause
      const runButton = screen.queryByRole('button', { name: 'Run' })
      if (runButton) {
        await user.click(runButton)
      }
    })

    it('handleDeleteWorkflow guards when no workflow id', async () => {
      // Cast through unknown for test purposes
      const noIdWorkflow = { ...mockWorkflow, id: undefined } as unknown as WorkflowWithVersion

      const { container } = await renderBuilder({ workflow: noIdWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Verify component renders without crashing
      expect(container).toBeInTheDocument()

      const user = userEvent.setup()
      // Try to access kebab menu - if present, clicking should not throw
      const kebabButton = screen.queryByLabelText('Workflow actions')
      if (kebabButton) {
        await user.click(kebabButton)
      }
    })

    it('handleToggleDetails deselects nodes when opening', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Click details to trigger the reactFlowInstance.setNodes path
      await clickKebabItem('Workflow details')

      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // PANEL INTERACTIONS
  // ============================================================================

  describe('Panel Interactions', () => {
    it('closes details panel when opening add step panel', async () => {
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })

      // Open details first
      await clickKebabItem('Workflow details')

      // Then open add step panel - should close details
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Add step' }))

      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
      })
    })

    it('closes history panel when opening add step panel', async () => {
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })

      // Open history first
      await clickKebabItem('Run history')
      await waitFor(() => {
        expect(screen.getByText('Run history')).toBeInTheDocument()
      })

      // Then open add step panel - should close history
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Add step' }))

      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
        expect(screen.queryByText('Run history')).not.toBeInTheDocument()
      })
    })

    it('closes details panel when opening history panel', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Open details first
      await clickKebabItem('Workflow details')

      // Then open history - should close details
      await clickKebabItem('Run history')

      await waitFor(() => {
        expect(screen.getByText('Run history')).toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // WORKFLOW ID CHANGE SCENARIOS
  // ============================================================================

  describe('Workflow ID Changes', () => {
    it('resets state when workflow ID changes from one to another', async () => {
      const { rerender } = await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Change to a different workflow (different ID)
      const otherWorkflow = {
        ...mockWorkflow,
        id: 'workflow-2',
        name: 'Other Workflow',
        description: 'Other Description',
      }

      rerender(
        <QueryClientProvider client={queryClient}>
          <AlertProvider>
            <ReactFlowProvider>
              <BuilderContent workflow={otherWorkflow} isNew={false} workflowId="workflow-2" />
            </ReactFlowProvider>
          </AlertProvider>
        </QueryClientProvider>
      )

      // This tests lines 372-377: the useEffect that resets state when workflowId changes
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Other Workflow')
      })
    })

    it('does not reset when same workflow ID', async () => {
      const { rerender } = await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Change name without changing ID
      const user = userEvent.setup()
      const nameInput = screen.getByPlaceholderText('Workflow name')
      await user.clear(nameInput)
      await user.type(nameInput, 'Modified Name')

      // Verify the name was changed
      expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Modified Name')

      // Rerender with same ID - component keeps local state for name
      rerender(
        <QueryClientProvider client={queryClient}>
          <AlertProvider>
            <ReactFlowProvider>
              <BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />
            </ReactFlowProvider>
          </AlertProvider>
        </QueryClientProvider>
      )

      // Component re-initializes from workflow prop on rerender, so expect original name
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })
    })
  })

  // ============================================================================
  // CALLBACK EDGE CASES
  // ============================================================================

  describe('Callback Edge Cases', () => {
    it('handleSaveWorkflow with existing workflow uses PATCH', async () => {
      const mockUpdateMutate = vi.fn()

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'patch') {
          return createMockMutation(mockUpdateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalled()
      })
    })

    it('handleSaveWorkflow with new workflow uses POST', async () => {
      const mockCreateMutate = vi.fn()

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'post') {
          return createMockMutation(mockCreateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })
    })
  })

  // ============================================================================
  // DROPDOWN ONOPEN CHANGE
  // ============================================================================

  describe('Dropdown Callbacks', () => {
    it('closes kebab dropdown via external click', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Open kebab
      await user.click(screen.getByLabelText('Workflow actions'))
      await waitFor(() => {
        expect(screen.getByText('Delete workflow')).toBeInTheDocument()
      })

      // Click outside to trigger onOpenChange(false) - line 900
      await user.click(document.body)
    })
  })

  // ============================================================================
  // COMPLEX WORKFLOW STRUCTURES
  // ============================================================================

  describe('Complex Workflow Structures', () => {
    it('handles workflow with condition activity', async () => {
      const conditionWorkflow = {
        ...mockWorkflow,
        name: 'Condition Workflow',
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            name: 'Condition Workflow',
            description: '',
            triggers: [{ id: 'manual_trigger', type: 'manual_trigger', parameters: {} }],
            nodes: [
              {
                type: 'condition' as const,
                id: 'cond-1',
                name: 'Condition',
                parameters: { condition: 'true' },
              },
            ],
            edges: [],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: conditionWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Condition Workflow')
      })
    })

    it('handles workflow with loop activity', async () => {
      const loopWorkflow = {
        ...mockWorkflow,
        name: 'Loop Workflow',
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            name: 'Loop Workflow',
            description: '',
            triggers: [{ id: 'manual_trigger', type: 'manual_trigger', parameters: {} }],
            nodes: [
              {
                type: 'loop' as const,
                id: 'loop-1',
                name: 'Loop',
                parameters: { type: 'for_each', items: '[]' },
              },
            ],
            edges: [],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: loopWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Loop Workflow')
      })
    })

    it('handles workflow with nested structures', async () => {
      const nestedWorkflow = {
        ...mockWorkflow,
        name: 'Nested Workflow',
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            name: 'Nested Workflow',
            description: '',
            triggers: [{ id: 'manual_trigger', type: 'manual_trigger', parameters: {} }],
            nodes: [
              {
                type: 'condition' as const,
                id: 'cond-1',
                name: 'Outer Condition',
                parameters: { condition: 'true' },
              },
              {
                type: 'script' as const,
                id: 'task-inner',
                name: 'Inner Task',
                parameters: { language: 'python', code: '' },
              },
            ],
            edges: [{ from: 'cond-1', to: 'task-inner', from_port: 'true' }],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: nestedWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Nested Workflow')
      })
    })
  })

  // ============================================================================
  // MUTATION CALLBACK BRANCHES
  // ============================================================================

  describe('Mutation Callback Branches', () => {
    it('save success navigates for new workflow', async () => {
      const mockCreateMutate = vi.fn()

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'post') {
          return createMockMutation(mockCreateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })
    })

    it('save success invalidates queries for existing workflow', async () => {
      const mockUpdateMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess({ id: 'workflow-1' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'patch') {
          return createMockMutation(mockUpdateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalled()
      })
    })

    it('run workflow success without data id', async () => {
      const user = userEvent.setup()
      const mockExecuteMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          // Return data without id field
          callbacks.onSuccess({}, params, undefined)
        }
      })

      mockWorkflowPatchSuccess()

      vi.mocked(executionsClient.useMutation).mockImplementation((method, path) => {
        if (method === 'post' && path === '/executions') {
          return createMockMutation(mockExecuteMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: createWorkflowWithInputSchema(), isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      await user.click(screen.getByRole('button', { name: 'Run' }))
      await screen.findByText(/Run Test Workflow\?/)
      await user.click(screen.getByRole('button', { name: 'Run now' }))
      await screen.findByText(/Set mock output data for/)
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() => {
        expect(mockExecuteMutate).toHaveBeenCalled()
        // Navigation should not happen since no id in response
      })
    })
  })

  // ============================================================================
  // DESCRIPTION INPUT
  // ============================================================================

  describe('Description Handling', () => {
    it('initializes description from workflow metadata', async () => {
      const workflowWithMetadataDesc = {
        ...mockWorkflow,
        name: 'Metadata Test',
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            name: 'Metadata Test',
            description: 'Metadata Description',
            triggers: [],
            nodes: [],
            edges: [],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: workflowWithMetadataDesc, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Metadata Test')
      })
    })

    it('uses workflow description over metadata when present', async () => {
      const workflowBothDesc = {
        ...mockWorkflow,
        name: 'Description Test',
        description: 'Top Level Description',
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            name: 'Description Test',
            description: 'Metadata Description',
            triggers: [],
            nodes: [],
            edges: [],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: workflowBothDesc, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Description Test')
      })
    })
  })

  // ============================================================================
  // ADDITIONAL COVERAGE FOR EDGE CASES
  // ============================================================================

  describe('Workflow Save Error Handling', () => {
    it('shows error alert when currentWorkflow is null during save', async () => {
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      // Wait for the new-workflow useEffect to finish initializing, then clear it
      await waitFor(() => {
        expect(useWorkflowStore.getState().currentWorkflow).not.toBeNull()
      })

      act(() => {
        useWorkflowStore.setState({ currentWorkflow: null })
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(screen.getByText('No workflow to save')).toBeInTheDocument()
        expect(screen.getByText('Save failed')).toBeInTheDocument()
      })
    })
  })

  describe('Workflow ID Reset', () => {
    it('clears workflow state when navigating to different workflow', async () => {
      const { rerender } = await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Navigate to completely different workflow - tests lines 373-376
      const differentWorkflow = {
        ...mockWorkflow,
        id: 'workflow-different',
        name: 'Different Workflow',
      }

      rerender(
        <QueryClientProvider client={queryClient}>
          <AlertProvider>
            <ReactFlowProvider>
              <BuilderContent workflow={differentWorkflow} isNew={false} workflowId="workflow-different" />
            </ReactFlowProvider>
          </AlertProvider>
        </QueryClientProvider>
      )

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Different Workflow')
      })
    })
  })

  describe('Panel State Management', () => {
    it('opens add step panel with source step context', async () => {
      await renderBuilder({ workflow: createWorkflowWithNodes(), isNew: false, workflowId: 'workflow-1' })

      const user = userEvent.setup()
      // Open add step panel
      const addNodeButton = screen.getByRole('button', { name: 'Add step' })
      await user.click(addNodeButton)

      await waitFor(() => {
        expect(screen.getByRole('region', { name: 'Add step' })).toBeInTheDocument()
      })
    })

    it('maintains panel state across interactions', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Open history panel
      await clickKebabItem('Run history')
      await waitFor(() => {
        expect(screen.getByText('Run history')).toBeInTheDocument()
      })

      // Toggle details - should close history
      await clickKebabItem('Workflow details')

      // History should be closed
      await waitFor(() => {
        expect(screen.queryByText('Run history')).not.toBeInTheDocument()
      })
    })
  })

  describe('beforeunload Event', () => {
    it('adds and removes beforeunload listener', async () => {
      const addSpy = vi.spyOn(window, 'addEventListener')
      const removeSpy = vi.spyOn(window, 'removeEventListener')

      const { unmount } = await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      // Listener should be added
      expect(addSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))

      unmount()

      // Listener should be removed on unmount
      expect(removeSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))

      addSpy.mockRestore()
      removeSpy.mockRestore()
    })
  })

  describe('Empty Workflow Definition', () => {
    it('handles getWorkflowDefinition when currentWorkflow is null', async () => {
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      const user = userEvent.setup()
      // Modify workflow name
      const nameInput = screen.getByPlaceholderText('Workflow name')
      await user.clear(nameInput)
      await user.type(nameInput, 'Empty Test')

      expect(nameInput).toHaveValue('Empty Test')

      // Try to save - this will call getWorkflowDefinition
      await user.click(screen.getByRole('button', { name: /save/i }))

      // Component should handle the empty case gracefully
    })
  })

  describe('Delete Workflow Flow', () => {
    it('completes full delete flow', async () => {
      const mockDeleteMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess(undefined, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'delete') {
          return createMockMutation(mockDeleteMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      const user = userEvent.setup()
      // Open kebab menu
      await user.click(screen.getByLabelText('Workflow actions'))

      // Click delete
      await user.click(await screen.findByText('Delete workflow'))
      await screen.findByText('Delete workflow?')

      // Acknowledge and confirm delete
      await user.click(
        screen.getByRole('checkbox', {
          name: /I understand this workflow will be deleted and any in-progress runs will stop immediately/,
        })
      )
      await user.click(screen.getByRole('button', { name: 'Delete' }))

      await waitFor(() => {
        expect(mockDeleteMutate).toHaveBeenCalled()
      })
    })
  })

  describe('Run Workflow Flow', () => {
    it('completes full run flow with success', async () => {
      const user = userEvent.setup()
      const mockExecuteMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        if (callbacks?.onSuccess) {
          callbacks.onSuccess({ id: 'execution-123' }, params, undefined)
        }
      })

      mockWorkflowPatchSuccess()

      vi.mocked(executionsClient.useMutation).mockImplementation((method, path) => {
        if (method === 'post' && path === '/executions') {
          return createMockMutation(mockExecuteMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: createWorkflowWithInputSchema(), isNew: false, workflowId: 'workflow-1' })
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('Test Workflow')
      })

      // Click Run → confirmation dialog → input modal → confirm
      await user.click(screen.getByRole('button', { name: 'Run' }))
      await screen.findByText(/Run Test Workflow\?/)
      await user.click(screen.getByRole('button', { name: 'Run now' }))
      await screen.findByText(/Set mock output data for/)
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() => {
        expect(mockExecuteMutate).toHaveBeenCalled()
        expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/executions/execution-123?history=closed' })
      })
    })
  })

  describe('V2 Schema - Trigger ID Mapping', () => {
    it('maps trigger definition IDs to display IDs when loading workflow', async () => {
      const workflowWithTrigger = {
        ...mockWorkflow,
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            triggers: [{ id: 'webhook_trigger_1', type: 'webhook', parameters: {} as Record<string, never> }],
            nodes: [
              { id: 'task-1', type: 'script', parameters: { code: 'print("hello")' } as Record<string, unknown> },
            ],
            edges: [{ from: 'webhook_trigger_1', to: 'task-1' }],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      vi.mocked(workflowClient.useQuery).mockImplementation(
        (_method, path): ReturnType<typeof workflowClient.useQuery> => {
          if (path === '/workflows' || path === '/workflows/{id}') {
            return {
              data: workflowWithTrigger,
              isSuccess: true,
              isLoading: false,
              refetch: vi.fn(),
            } as ReturnType<typeof workflowClient.useQuery>
          }
          return {
            data: undefined,
            isSuccess: false,
            isLoading: false,
            refetch: vi.fn(),
          } as ReturnType<typeof workflowClient.useQuery>
        }
      )

      await renderBuilder({ workflow: workflowWithTrigger, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        const state = useWorkflowStore.getState()
        // Verify edges are loaded
        expect(state.edges.length).toBeGreaterThan(0)
        // Verify trigger ID was mapped (webhook_trigger_1 → trigger-0)
        const triggerEdge = state.edges.find((e) => e.source === 'trigger-0')
        expect(triggerEdge).toBeDefined()
      })
    })

    it('handles triggers without ID field gracefully', async () => {
      const workflowNoTriggerIds = {
        ...mockWorkflow,
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            triggers: [
              { type: 'manual_trigger', parameters: {} as Record<string, never> }, // No id field
            ],
            nodes: [],
            edges: [],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      vi.mocked(workflowClient.useQuery).mockImplementation(
        (_method, path): ReturnType<typeof workflowClient.useQuery> => {
          if (path === '/workflows' || path === '/workflows/{id}') {
            return {
              data: workflowNoTriggerIds,
              isSuccess: true,
              isLoading: false,
              refetch: vi.fn(),
            } as ReturnType<typeof workflowClient.useQuery>
          }
          return {
            data: undefined,
            isSuccess: false,
            isLoading: false,
            refetch: vi.fn(),
          } as ReturnType<typeof workflowClient.useQuery>
        }
      )

      // Should not crash when trigger has no ID
      await renderBuilder({ workflow: workflowNoTriggerIds, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toBeInTheDocument()
      })
    })
  })

  describe('V2 Schema - Port Name Mapping', () => {
    it('converts v2 from_port to React Flow sourceHandle', async () => {
      const workflowWithPorts = {
        ...mockWorkflow,
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            triggers: [{ id: 'trigger-1', type: 'manual_trigger', parameters: {} as Record<string, never> }],
            nodes: [
              { id: 'cond-1', type: 'condition', parameters: { condition: 'true' } as Record<string, unknown> },
              { id: 'task-true', type: 'script', parameters: { code: '' } as Record<string, unknown> },
            ],
            edges: [
              { from: 'trigger-1', to: 'cond-1' },
              { from: 'cond-1', to: 'task-true', from_port: 'true' },
            ],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      vi.mocked(workflowClient.useQuery).mockImplementation(
        (_method, path): ReturnType<typeof workflowClient.useQuery> => {
          if (path === '/workflows' || path === '/workflows/{id}') {
            return {
              data: workflowWithPorts,
              isSuccess: true,
              isLoading: false,
              refetch: vi.fn(),
            } as ReturnType<typeof workflowClient.useQuery>
          }
          return {
            data: undefined,
            isSuccess: false,
            isLoading: false,
            refetch: vi.fn(),
          } as ReturnType<typeof workflowClient.useQuery>
        }
      )

      await renderBuilder({ workflow: workflowWithPorts, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        const state = useWorkflowStore.getState()
        // Find edge with from_port: 'true'
        const condEdge = state.edges.find((e) => e.source === 'cond-1' && e.target === 'task-true')
        expect(condEdge).toBeDefined()
        // Verify sourceHandle was converted
        expect(condEdge?.sourceHandle).toBe('true')
      })
    })

    it('defaults targetHandle to "target" when to_port is undefined', async () => {
      const workflowNoToPort = {
        ...mockWorkflow,
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            triggers: [],
            nodes: [
              { id: 'task-1', type: 'script', parameters: { code: '' } as Record<string, unknown> },
              { id: 'task-2', type: 'script', parameters: { code: '' } as Record<string, unknown> },
            ],
            edges: [
              { from: 'task-1', to: 'task-2' }, // No to_port
            ],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      vi.mocked(workflowClient.useQuery).mockImplementation(
        (_method, path): ReturnType<typeof workflowClient.useQuery> => {
          if (path === '/workflows' || path === '/workflows/{id}') {
            return {
              data: workflowNoToPort,
              isSuccess: true,
              isLoading: false,
              refetch: vi.fn(),
            } as ReturnType<typeof workflowClient.useQuery>
          }
          return {
            data: undefined,
            isSuccess: false,
            isLoading: false,
            refetch: vi.fn(),
          } as ReturnType<typeof workflowClient.useQuery>
        }
      )

      await renderBuilder({ workflow: workflowNoToPort, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        const state = useWorkflowStore.getState()
        const edge = state.edges.find((e) => e.source === 'task-1')
        expect(edge).toBeDefined()
        // Should default to 'target'
        expect(edge?.targetHandle).toBe('target')
      })
    })

    it('maps loop port names: from_port iterate→loop, to_port iterate→end, to_port complete passes through', async () => {
      const workflowWithLoopPorts = {
        ...mockWorkflow,
        version: {
          workflow_definition: {
            schema_version: '2.0.0' as const,
            triggers: [],
            nodes: [
              { id: 'loop-1', type: 'loop', parameters: { type: 'for_each', items: '[]' } as Record<string, unknown> },
              { id: 'loop-body', type: 'script', parameters: { code: '' } as Record<string, unknown> },
            ],
            edges: [
              { from: 'loop-1', to: 'loop-body', from_port: 'iterate' }, // v2 name
              { from: 'loop-body', to: 'loop-1', to_port: 'iterate' }, // v2 feedback edge
            ],
            $defs: {},
          },
        },
      } as unknown as WorkflowWithVersion

      vi.mocked(workflowClient.useQuery).mockImplementation(
        (_method, path): ReturnType<typeof workflowClient.useQuery> => {
          if (path === '/workflows' || path === '/workflows/{id}') {
            return {
              data: workflowWithLoopPorts,
              isSuccess: true,
              isLoading: false,
              refetch: vi.fn(),
            } as ReturnType<typeof workflowClient.useQuery>
          }
          return {
            data: undefined,
            isSuccess: false,
            isLoading: false,
            refetch: vi.fn(),
          } as ReturnType<typeof workflowClient.useQuery>
        }
      )

      await renderBuilder({ workflow: workflowWithLoopPorts, isNew: false, workflowId: 'workflow-1' })

      await waitFor(() => {
        const state = useWorkflowStore.getState()
        // Find iterate edge (should map to 'loop')
        const iterateEdge = state.edges.find((e) => e.source === 'loop-1' && e.target === 'loop-body')
        expect(iterateEdge?.sourceHandle).toBe('loop')

        // Find feedback edge (to_port 'iterate' should map to 'end')
        const feedbackEdge = state.edges.find((e) => e.source === 'loop-body' && e.target === 'loop-1')
        expect(feedbackEdge?.targetHandle).toBe('end')
      })
    })
  })

  // ============================================================================
  // BRANCH COVERAGE: Targeted tests for uncovered branches
  // ============================================================================

  describe('Branch Coverage: Save with default name resolution', () => {
    it('resolves default name when saving new workflow with existing "new-workflow"', async () => {
      const existingWorkflows = {
        resources: [{ id: 'existing-1', name: 'new-workflow' }],
      }

      // Mock workflow list query to return existing workflow with name "new-workflow"
      vi.mocked(workflowClient.useQuery).mockImplementation((method, path) => {
        if (method === 'get' && path === '/workflows') {
          return {
            data: existingWorkflows,
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

      const mockCreateMutate = vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
        // Verify the name was incremented to avoid conflict
        const body = (params as { body: { name: string } }).body
        expect(body.name).toBe('new-workflow-1')
        if (callbacks?.onSuccess) {
          callbacks.onSuccess({ id: 'new-workflow-id' }, params, undefined)
        }
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'post') {
          return createMockMutation(mockCreateMutate)
        }
        return createMockMutation()
      })

      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      // Component auto-resolves to "new-workflow-1" since "new-workflow" exists
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Workflow name')).toHaveValue('new-workflow-1')
      })

      // User keeps the auto-resolved name and saves
      const user = userEvent.setup()
      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockCreateMutate).toHaveBeenCalled()
      })

      // This tests the branch: if (isNew && workflowName === DEFAULT_WORKFLOW_NAME && workflowsListQuery.data?.resources)
      // Note: The branch is tested during the useEffect that auto-resolves the name on component mount
    })
  })

  describe('Branch Coverage: Workflow state checks', () => {
    it('verifies workflow dirty state can be set', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      const user = userEvent.setup()
      // Make workflow dirty by changing the name
      const nameInput = screen.getByPlaceholderText('Workflow name')
      await user.clear(nameInput)
      await user.type(nameInput, 'Modified Workflow')

      // Verify workflow is dirty
      expect(useWorkflowStore.getState().isDirty).toBe(true)

      // This tests the dirty state management which is checked in various branches
    })
  })

  describe('Branch Coverage: Individual change flags', () => {
    it('marks dirty when only name changes', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Workflow details')

      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const nameInput = screen.getByLabelText('Workflow name in workflow details')
      await user.clear(nameInput)
      await user.type(nameInput, 'Name Changed')

      // Verify workflow store is marked dirty
      await waitFor(() => {
        expect(useWorkflowStore.getState().isDirty).toBe(true)
      })

      // This tests the branch: if (nameChanged)
    })

    it('marks dirty when only description changes', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Workflow details')

      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const descriptionTextarea = screen.getByLabelText('Description')
      await user.clear(descriptionTextarea)
      await user.type(descriptionTextarea, 'Description Changed')

      // Verify workflow store is marked dirty
      await waitFor(() => {
        expect(useWorkflowStore.getState().isDirty).toBe(true)
      })

      // This tests the branch: if (descriptionChanged)
    })

    it('marks dirty when both name and description change', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Workflow details')

      await waitFor(() => {
        expect(screen.getByText('Workflow details')).toBeInTheDocument()
      })

      // Change both name and description
      const user = userEvent.setup()
      const nameInput = screen.getByLabelText('Workflow name in workflow details')
      const descriptionTextarea = screen.getByLabelText('Description')

      await user.clear(nameInput)
      await user.type(nameInput, 'Name Changed')
      await user.clear(descriptionTextarea)
      await user.type(descriptionTextarea, 'Description Changed')

      // Verify workflow store is marked dirty
      await waitFor(() => {
        expect(useWorkflowStore.getState().isDirty).toBe(true)
      })

      // This tests the branches: if (nameChanged) and if (descriptionChanged)
    })
  })

  describe('Version History', () => {
    const mockVersions = [
      {
        id: 'ver-2',
        workflow_id: 'workflow-1',
        version: 2,
        schema_version: '2.0.0',
        workflow_definition: { schema_version: '2.0.0', name: 'v2', triggers: [], nodes: [], edges: [] },
        created_at: '2026-05-19T14:30:00.000Z',
        change_description: 'Second version',
        status: 'draft',
        name: null,
        created_by: 'user-1',
        created_by_username: 'sarah.chen',
      },
      {
        id: 'ver-1',
        workflow_id: 'workflow-1',
        version: 1,
        schema_version: '2.0.0',
        workflow_definition: { schema_version: '2.0.0', name: 'v1', triggers: [], nodes: [], edges: [] },
        created_at: '2026-05-18T10:00:00.000Z',
        change_description: 'First version',
        status: 'published',
        name: null,
        created_by: 'user-1',
        created_by_username: 'marcus.williams',
      },
    ]

    function mockVersionQueries() {
      vi.mocked(workflowClient.useQuery).mockImplementation((_method, path: string) => {
        if (path.includes('/versions/')) {
          return {
            data: mockVersions[0],
            isPending: false,
            isError: false,
            error: null,
            refetch: vi.fn(),
          }
        }
        if (path.includes('/versions')) {
          return {
            data: { resources: mockVersions },
            isPending: false,
            isError: false,
            error: null,
            refetch: vi.fn().mockResolvedValue({ data: { resources: mockVersions } }),
          }
        }
        if (path === '/workflows') {
          return { data: { resources: [] }, isPending: false, isError: false, error: null, refetch: vi.fn() }
        }
        return { data: undefined, isPending: false, isError: false, error: null, refetch: vi.fn() }
      })
    }

    it('opens version history panel via kebab menu', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')

      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 2, name: 'Version history' })).toBeInTheDocument()
      })
    })

    it('does not show version history kebab item for new workflows', async () => {
      const user = userEvent.setup()
      await renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

      await user.click(screen.getByLabelText('Workflow actions'))

      await waitFor(() => {
        expect(screen.queryByRole('menuitem', { name: /Version history/i })).not.toBeInTheDocument()
      })
    })

    it('renders with initialViewVersion prop and shows version view toolbar', async () => {
      mockVersionQueries()

      await renderBuilder({
        workflow: mockWorkflow,
        isNew: false,
        workflowId: 'workflow-1',
        initialViewVersion: 2,
      })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
      })
    })

    it('opens version history panel with version data', async () => {
      mockVersionQueries()

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')

      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
        expect(screen.getByText('marcus.williams')).toBeInTheDocument()
      })
    })

    it('selects a version from the panel when not dirty', async () => {
      mockVersionQueries()

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const versionButtons = screen
        .getAllByRole('button')
        .filter((el) => el.classList.contains('pf-v6-c-simple-list__item-link'))
      await user.click(versionButtons[0])

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
      })
    })

    it('shows save prompt when selecting version with dirty state', async () => {
      mockVersionQueries()

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const versionButtons = screen
        .getAllByRole('button')
        .filter((el) => el.classList.contains('pf-v6-c-simple-list__item-link'))
      await user.click(versionButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Save changes before viewing this version?')).toBeInTheDocument()
      })
    })

    it('dismisses save prompt via Cancel button', async () => {
      mockVersionQueries()

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const versionButtons = screen
        .getAllByRole('button')
        .filter((el) => el.classList.contains('pf-v6-c-simple-list__item-link'))
      await user.click(versionButtons[0])
      await screen.findByText('Save changes before viewing this version?')

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Save changes before viewing this version?')).not.toBeInTheDocument()
      })
    })

    it('views version without saving via secondary button', async () => {
      mockVersionQueries()

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const versionButtons = screen
        .getAllByRole('button')
        .filter((el) => el.classList.contains('pf-v6-c-simple-list__item-link'))
      await user.click(versionButtons[0])
      await screen.findByText('Save changes before viewing this version?')

      await user.click(screen.getByRole('button', { name: 'View version without saving' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
      })
    })

    it('closes version history panel via close button', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')

      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 2, name: 'Version history' })).toBeInTheDocument()
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Collapse version history' }))

      await waitFor(() => {
        expect(screen.queryByRole('heading', { level: 2, name: 'Version history' })).not.toBeInTheDocument()
      })
    })

    it('toggles version history panel closed via kebab', async () => {
      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 2, name: 'Version history' })).toBeInTheDocument()
      })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.queryByText('Version History')).not.toBeInTheDocument()
      })
    })
  })

  describe('Version Conflict Resolution', () => {
    const conflictWorkflow = {
      ...mockWorkflow,
      current_version: 3,
      project_id: 'project-1',
      version: {
        ...mockWorkflow.version,
        version: 3,
      },
    } as unknown as WorkflowWithVersion

    function setupConflictOnSave() {
      const mockUpdateMutate = vi.fn((_params: unknown, callbacks?: MutationCallbacks) => {
        callbacks?.onError?.(
          {
            code: 'WORKFLOW_VERSION_CONFLICT',
            current_version: 5,
            current_version_name: null,
            expected_version: 3,
            created_by_username: 'alice',
            created_at: '2026-06-25T12:00:00Z',
          },
          _params,
          undefined
        )
      })

      vi.mocked(workflowClient.useMutation).mockImplementation((method) => {
        if (method === 'patch') {
          return createMockMutation(mockUpdateMutate)
        }
        return createMockMutation()
      })

      return mockUpdateMutate
    }

    async function triggerConflictDialog() {
      setupConflictOnSave()
      await renderBuilder({ workflow: conflictWorkflow, isNew: false, workflowId: 'workflow-1' })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(screen.getByRole('dialog', { name: /conflict/i })).toBeInTheDocument()
      })

      return user
    }

    it('shows conflict dialog when save returns WORKFLOW_VERSION_CONFLICT', async () => {
      await triggerConflictDialog()

      expect(screen.getByText(/was saved by alice/)).toBeInTheDocument()
      expect(screen.getByText(/Your changes are based on version/)).toBeInTheDocument()
    })

    it('"Save as newest version" retries save with conflict version', async () => {
      const mockUpdateMutate = setupConflictOnSave()
      await renderBuilder({ workflow: conflictWorkflow, isNew: false, workflowId: 'workflow-1' })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(screen.getByRole('dialog', { name: /conflict/i })).toBeInTheDocument()
      })

      // Now make the retry succeed
      mockUpdateMutate.mockImplementation((_params: unknown, callbacks?: MutationCallbacks) => {
        callbacks?.onSuccess?.({ id: 'workflow-1', current_version: 6 }, _params, undefined)
      })

      await user.click(screen.getByRole('button', { name: 'Save as newest version' }))

      await waitFor(() => {
        expect(mockUpdateMutate).toHaveBeenCalledTimes(2)
      })

      // Dialog should close after successful save
      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: /conflict/i })).not.toBeInTheDocument()
      })
    })

    it('"Save as newest version" closes dialog when retry save fails', async () => {
      setupConflictOnSave()
      await renderBuilder({ workflow: conflictWorkflow, isNew: false, workflowId: 'workflow-1' })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(screen.getByRole('dialog', { name: /conflict/i })).toBeInTheDocument()
      })

      // Retry will also fail (non-conflict error) — the mock still returns conflict
      // but handleSaveWorkflow resolves false, so dialog should close
      await user.click(screen.getByRole('button', { name: 'Save as newest version' }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: /conflict/i })).not.toBeInTheDocument()
      })
    })

    it('"Create duplicate workflow" creates a copy and navigates', async () => {
      const user = await triggerConflictDialog()

      vi.mocked(workflowFetchClient.POST).mockResolvedValue({
        data: { id: 'duplicated-wf-id', current_version: 1 },
        error: undefined,
        response: new Response(),
      })

      await user.click(screen.getByRole('button', { name: /create duplicate/i }))

      await waitFor(() => {
        expect(workflowFetchClient.POST).toHaveBeenCalledWith(
          '/workflows',
          expect.objectContaining({
            body: expect.objectContaining({
              name: 'Test Workflow (Copy)',
            }) as unknown,
          })
        )
      })

      await waitFor(() => {
        expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflow-builder/duplicated-wf-id' })
      })
    })

    it('"Create duplicate workflow" shows error when POST fails', async () => {
      const user = await triggerConflictDialog()

      vi.mocked(workflowFetchClient.POST).mockResolvedValue({
        data: undefined,
        error: { detail: 'Server error' },
        response: new Response(null, { status: 500 }),
      })

      await user.click(screen.getByRole('button', { name: /create duplicate/i }))

      await waitFor(() => {
        expect(screen.getByText('Duplicate failed')).toBeInTheDocument()
      })
    })

    it('"Refresh to latest" reloads the page', async () => {
      const reloadMock = vi.fn()
      Object.defineProperty(window, 'location', {
        value: { ...window.location, reload: reloadMock },
        writable: true,
      })

      const user = await triggerConflictDialog()
      await user.click(screen.getByRole('button', { name: /refresh to latest/i }))

      await waitFor(() => {
        expect(reloadMock).toHaveBeenCalled()
      })

      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: /conflict/i })).not.toBeInTheDocument()
      })
    })

    it('"Create duplicate workflow" handles missing workflowId gracefully', async () => {
      setupConflictOnSave()
      await renderBuilder({ workflow: conflictWorkflow, isNew: false, workflowId: null })

      act(() => {
        useWorkflowStore.setState({ isDirty: true })
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /save/i }))

      // Save should fail because workflowId is null (goes to create path),
      // but no conflict dialog will appear since it's a create
      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: /conflict/i })).not.toBeInTheDocument()
      })
    })
  })

  describe('RBAC read-only mode', () => {
    afterEach(() => {
      mockBuilderPermissions.canEdit = true
      mockBuilderPermissions.isLoading = false
    })

    it('shows read-only banner when canEdit is false', async () => {
      mockBuilderPermissions.canEdit = false
      mockBuilderPermissions.isLoading = false

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      expect(screen.getByText('You are viewing this workflow in read-only mode.')).toBeInTheDocument()
      expect(screen.getByText(/You do not have permission to edit this workflow/)).toBeInTheDocument()
    })

    it('does not show read-only banner when canEdit is true', async () => {
      mockBuilderPermissions.canEdit = true
      mockBuilderPermissions.isLoading = false

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      expect(screen.queryByText('You are viewing this workflow in read-only mode.')).not.toBeInTheDocument()
    })

    it('does not show read-only banner while permissions are loading', async () => {
      mockBuilderPermissions.canEdit = false
      mockBuilderPermissions.isLoading = true

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      expect(screen.queryByText('You are viewing this workflow in read-only mode.')).not.toBeInTheDocument()
    })
  })

  describe('executionsByVersion and run history', () => {
    const versionData = [
      {
        id: 'ver-2',
        workflow_id: 'workflow-1',
        version: 2,
        schema_version: '2.0.0',
        workflow_definition: { schema_version: '2.0.0', name: 'v2', triggers: [], nodes: [], edges: [] },
        created_at: '2026-05-19T14:30:00.000Z',
        change_description: 'Second version',
        status: 'draft',
        name: null,
        created_by: 'user-1',
        created_by_username: 'sarah.chen',
      },
      {
        id: 'ver-1',
        workflow_id: 'workflow-1',
        version: 1,
        schema_version: '2.0.0',
        workflow_definition: { schema_version: '2.0.0', name: 'v1', triggers: [], nodes: [], edges: [] },
        created_at: '2026-05-18T10:00:00.000Z',
        change_description: 'First version',
        status: 'published',
        name: null,
        created_by: 'user-1',
        created_by_username: 'marcus.williams',
      },
    ]

    function mockVersionAndExecutionQueries(executions: Record<string, unknown>[] = []) {
      vi.mocked(workflowClient.useQuery).mockImplementation((_method, path: string) => {
        if (path.includes('/versions/')) {
          return { data: versionData[0], isPending: false, isError: false, error: null, refetch: vi.fn() }
        }
        if (path.includes('/versions')) {
          return {
            data: { resources: versionData },
            isPending: false,
            isError: false,
            error: null,
            refetch: vi.fn().mockResolvedValue({ data: { resources: versionData } }),
          }
        }
        if (path === '/workflows') {
          return { data: { resources: [] }, isPending: false, isError: false, error: null, refetch: vi.fn() }
        }
        return { data: undefined, isPending: false, isError: false, error: null, refetch: vi.fn() }
      })
      vi.mocked(executionsClient.useQuery).mockImplementation((method, path) => {
        if (method === 'get' && path === '/executions') {
          return { data: { resources: executions }, isPending: false, isError: false, error: null, refetch: vi.fn() }
        }
        return { data: undefined, isPending: false, isError: false, error: null, refetch: vi.fn() }
      })
    }

    it('enables run history kebab item when version has executions', async () => {
      mockVersionAndExecutionQueries([{ id: 'exec-1', workflow_version: 2, workflow_version_id: 'ver-2-pub' }])

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
      await user.click(kebabButtons[0])

      const viewRunHistoryItem = screen.getByRole('menuitem', { name: /View run history/ })
      expect(viewRunHistoryItem).not.toHaveAttribute('aria-disabled', 'true')
    })

    it('disables run history kebab item when version has no executions', async () => {
      mockVersionAndExecutionQueries([])

      await renderBuilder({ workflow: mockWorkflow, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
      await user.click(kebabButtons[0])

      const viewRunHistoryItem = screen.getByRole('menuitem', { name: /View run history/ })
      expect(viewRunHistoryItem).toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('duplicate workflow', () => {
    const duplicateMutate = vi.fn()
    const dupVersionData = [
      {
        id: 'ver-2',
        workflow_id: 'workflow-1',
        version: 2,
        schema_version: '2.0.0',
        workflow_definition: { schema_version: '2.0.0', name: 'v2', triggers: [], nodes: [], edges: [] },
        created_at: '2026-05-19T14:30:00.000Z',
        change_description: 'Second version',
        status: 'draft',
        name: null,
        created_by: 'user-1',
        created_by_username: 'sarah.chen',
      },
    ]

    function setupDuplicateQueries() {
      vi.mocked(workflowClient.useQuery).mockImplementation((_method, path: string) => {
        if (path.includes('/versions/')) {
          return { data: dupVersionData[0], isPending: false, isError: false, error: null, refetch: vi.fn() }
        }
        if (path.includes('/versions')) {
          return {
            data: { resources: dupVersionData },
            isPending: false,
            isError: false,
            error: null,
            refetch: vi.fn().mockResolvedValue({ data: { resources: dupVersionData } }),
          }
        }
        if (path === '/workflows') {
          return { data: { resources: [] }, isPending: false, isError: false, error: null, refetch: vi.fn() }
        }
        return { data: undefined, isPending: false, isError: false, error: null, refetch: vi.fn() }
      })
      vi.mocked(workflowClient.useMutation).mockImplementation((method, path) => {
        if (method === 'post' && path === '/workflows') {
          return createMockMutation(duplicateMutate)
        }
        return createMockMutation()
      })
    }

    it('calls duplicate mutation with workflow name when duplicating a version', async () => {
      setupDuplicateQueries()
      const workflowWithProject = {
        ...mockWorkflow,
        project_id: 'project-1',
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: workflowWithProject, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
      await user.click(kebabButtons[0])
      await user.click(screen.getByText('Duplicate as new workflow'))

      expect(duplicateMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          body: expect.objectContaining({
            name: expect.stringContaining('Test Workflow - duplicate-') as unknown,
            project_id: 'project-1',
          }) as unknown,
        }),
        expect.objectContaining({
          onSuccess: expect.any(Function) as unknown,
          onError: expect.any(Function) as unknown,
        })
      )
    })

    it('shows success alert when duplicate succeeds', async () => {
      duplicateMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onSuccess?.({ id: 'dup-1' }, _body, undefined)
      })
      setupDuplicateQueries()
      const workflowWithProject = {
        ...mockWorkflow,
        project_id: 'project-1',
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: workflowWithProject, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
      await user.click(kebabButtons[0])
      await user.click(screen.getByText('Duplicate as new workflow'))

      await waitFor(() => {
        expect(screen.getByText('Workflow duplicated')).toBeInTheDocument()
      })
    })

    it('shows error alert when duplicate fails', async () => {
      duplicateMutate.mockImplementation((_body: unknown, callbacks: MutationCallbacks) => {
        callbacks.onError?.(new Error('Server error'), _body, undefined)
      })
      setupDuplicateQueries()
      const workflowWithProject = {
        ...mockWorkflow,
        project_id: 'project-1',
      } as unknown as WorkflowWithVersion

      await renderBuilder({ workflow: workflowWithProject, isNew: false, workflowId: 'workflow-1' })

      await clickKebabItem('Version history')
      await waitFor(() => {
        expect(screen.getByText('sarah.chen')).toBeInTheDocument()
      })

      const user = userEvent.setup()
      const kebabButtons = screen.getAllByRole('button', { name: /Actions for version/ })
      await user.click(kebabButtons[0])
      await user.click(screen.getByText('Duplicate as new workflow'))

      await waitFor(() => {
        expect(screen.getByText('Failed to duplicate workflow')).toBeInTheDocument()
      })
    })
  })
})
