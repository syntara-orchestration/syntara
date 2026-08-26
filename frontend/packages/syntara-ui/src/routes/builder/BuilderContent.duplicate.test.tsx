import type { WorkflowWithVersion } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReactFlowProvider } from '@xyflow/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { approvalsClient, executionsClient, workflowClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { routerTestState } from '../../test/setup'

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
    requestNavigation: vi.fn(),
  }),
}))

const mockBuilderPermissions = vi.hoisted(() => ({
  canEdit: true,
  canCreate: true,
  canRun: true,
  canDelete: true,
  isLoading: false,
  tooltips: { edit: '', save: '', publish: '', unpublish: '', run: '', delete: '', create: '' },
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
      <ReactFlowProvider>{children}</ReactFlowProvider>
    </AlertProvider>
  </QueryClientProvider>
)

const mockWorkflow: WorkflowWithVersion = {
  id: 'workflow-1',
  name: 'Test Workflow',
  description: 'Test Description',
  project_id: 'project-1',
  labels: { env: 'test' },
  published_version_id: null,
  is_enabled: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  created_by: 'user-1',
  is_builtin: false,
  current_version: 1,
  version: {
    id: 'version-1',
    workflow_id: 'workflow-1',
    version: 1,
    schema_version: '2.0.0',
    name: 'Version 1',
    workflow_definition: {
      name: 'Test Workflow',
      description: 'Test Description',
      nodes: [
        {
          id: 'activity-1',
          type: 'http_request',
          position: { x: 0, y: 0 },
          parameters: { url: 'https://example.com' },
        },
      ],
      edges: [],
    },
    created_by: 'user-1',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
}

describe('BuilderContent - Duplicate Workflow', () => {
  let mockDuplicateMutate: ReturnType<typeof vi.fn>
  let mockUpdateMutate: ReturnType<typeof vi.fn>
  let mockExecuteMutate: ReturnType<typeof vi.fn>

  async function openKebabAndClickDuplicate(user: ReturnType<typeof userEvent.setup>) {
    const kebabButton = screen.getByRole('button', { name: /Workflow actions/i })
    await user.click(kebabButton)
    const duplicateItem = await screen.findByRole('menuitem', { name: /Duplicate workflow/i })
    await user.click(duplicateItem)
  }

  beforeEach(() => {
    vi.clearAllMocks()
    routerTestState.pathname = '/workflow-builder/workflow-1'

    useWorkflowStore.setState({
      currentWorkflow: {
        schema_version: '2.0.0',
        name: 'Test Workflow',
        workflow: { activities: [] },
        triggers: [],
        is_builtin: false,
      },
      edges: [],
      nodePositions: {},
      isDirty: false,
      validationErrorCount: 0,
    })

    mockDuplicateMutate = vi.fn()
    mockUpdateMutate = vi.fn()
    mockExecuteMutate = vi.fn()

    vi.mocked(workflowClient.useQuery).mockImplementation((method: string, path: string) => {
      if (method === 'get' && path === '/workflows') {
        return {
          data: { resources: [mockWorkflow], has_more: false },
          isLoading: false,
          error: null,
          isPending: false,
          refetch: vi.fn(),
        } as never
      }
      return {
        data: { resources: [], has_more: false },
        isLoading: false,
        error: null,
        isPending: false,
        refetch: vi.fn(),
      } as never
    })

    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: { resources: [], has_more: false },
      isLoading: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)

    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: mockExecuteMutate,
      isPending: false,
    } as never)

    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      isPending: false,
      refetch: vi.fn(),
    } as never)

    vi.mocked(workflowClient.useMutation).mockImplementation((method: string, path: string) => {
      if (method === 'post' && path === '/workflows') {
        return {
          mutate: mockDuplicateMutate,
          isPending: false,
        } as never
      }
      if (method === 'patch' && path === '/workflows/{workflow_id}') {
        return {
          mutate: mockUpdateMutate,
          isPending: false,
        } as never
      }
      return {
        mutate: vi.fn(),
        isPending: false,
      } as never
    })
  })

  afterEach(() => {
    useWorkflowStore.temporal.getState().clear()
  })

  it('duplicates workflow with timestamp suffix', async () => {
    const user = userEvent.setup()
    const originalDateNow = Date.now
    Date.now = vi.fn(() => 1234567890)

    render(<BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())

    await openKebabAndClickDuplicate(user)

    await waitFor(() => expect(mockDuplicateMutate).toHaveBeenCalled())

    const callArgs = mockDuplicateMutate.mock.calls[0]?.[0] as
      | { body: { name: string; description: string; project_id: string; labels: Record<string, string> } }
      | undefined
    expect(callArgs).toBeDefined()
    expect(callArgs?.body.name).toContain('Test Workflow - duplicate-')
    expect(callArgs?.body.description).toBe('Test Description')
    expect(callArgs?.body.project_id).toBe('project-1')
    expect(callArgs?.body.labels).toEqual({ env: 'test' })

    Date.now = originalDateNow
  })

  it('guards against duplicating without current workflow', () => {
    useWorkflowStore.setState({ currentWorkflow: null })
    const state = useWorkflowStore.getState()
    expect(state.currentWorkflow).toBeNull()
  })

  it('shows success alert after duplication', async () => {
    const user = userEvent.setup()

    mockDuplicateMutate.mockImplementation((vars: never, callbacks: MutationCallbacks) => {
      callbacks.onSuccess?.({ id: 'new-workflow-id', name: 'Test Workflow - duplicate-xyz' }, vars, undefined)
    })

    render(<BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    await openKebabAndClickDuplicate(user)

    expect(await screen.findByText('Workflow duplicated')).toBeInTheDocument()
    expect(screen.getByText(/Created "Test Workflow - duplicate-/)).toBeInTheDocument()
  })

  it('navigates immediately when no unsaved changes', async () => {
    const user = userEvent.setup()

    mockDuplicateMutate.mockImplementation((vars: never, callbacks: MutationCallbacks) => {
      callbacks.onSuccess?.({ id: 'new-workflow-id' }, vars, undefined)
    })

    render(<BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    await openKebabAndClickDuplicate(user)

    expect(await screen.findByText('Workflow duplicated')).toBeInTheDocument()

    const openLink = screen.getByRole('button', { name: /Open workflow/i })
    await user.click(openLink)

    await waitFor(() => expect(routerTestState.pathname).toBe('/workflow-builder/new-workflow-id'))
  })

  it('shows save dialog when unsaved changes exist', async () => {
    const user = userEvent.setup()

    mockDuplicateMutate.mockImplementation((vars: never, callbacks: MutationCallbacks) => {
      callbacks.onSuccess?.({ id: 'new-workflow-id' }, vars, undefined)
    })

    render(<BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    act(() => useWorkflowStore.setState({ isDirty: true }))
    await openKebabAndClickDuplicate(user)

    expect(await screen.findByText('Workflow duplicated')).toBeInTheDocument()

    const openLink = screen.getByRole('button', { name: /Open workflow/i })
    await user.click(openLink)

    expect(await screen.findByText('Save changes before opening the duplicated workflow?')).toBeInTheDocument()
  })

  it('navigates without saving when confirmed', async () => {
    const user = userEvent.setup()

    mockDuplicateMutate.mockImplementation((vars: never, callbacks: MutationCallbacks) => {
      callbacks.onSuccess?.({ id: 'new-workflow-id' }, vars, undefined)
    })

    render(<BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    act(() => useWorkflowStore.setState({ isDirty: true }))
    await openKebabAndClickDuplicate(user)
    expect(await screen.findByText('Workflow duplicated')).toBeInTheDocument()

    const openLink = screen.getByRole('button', { name: /Open workflow/i })
    await user.click(openLink)

    expect(await screen.findByText('Save changes before opening the duplicated workflow?')).toBeInTheDocument()

    const openWithoutSaving = screen.getByRole('button', { name: /Open without saving/i })
    await user.click(openWithoutSaving)

    await waitFor(() => expect(routerTestState.pathname).toBe('/workflow-builder/new-workflow-id'))
  })

  it('closes dialog when cancelled', async () => {
    const user = userEvent.setup()

    mockDuplicateMutate.mockImplementation((vars: never, callbacks: MutationCallbacks) => {
      callbacks.onSuccess?.({ id: 'new-workflow-id' }, vars, undefined)
    })

    render(<BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    act(() => useWorkflowStore.setState({ isDirty: true }))
    await openKebabAndClickDuplicate(user)
    expect(await screen.findByText('Workflow duplicated')).toBeInTheDocument()

    const openLink = screen.getByRole('button', { name: /Open workflow/i })
    await user.click(openLink)

    expect(await screen.findByText('Save changes before opening the duplicated workflow?')).toBeInTheDocument()

    const cancelButton = screen.getByRole('button', { name: 'Cancel' })
    await user.click(cancelButton)

    await waitFor(() => {
      expect(screen.queryByText('Save changes before opening the duplicated workflow?')).not.toBeInTheDocument()
    })

    expect(routerTestState.pathname).toBe('/workflow-builder/workflow-1')
  })

  it('shows error when duplication fails', async () => {
    const user = userEvent.setup()

    mockDuplicateMutate.mockImplementation((vars: never, callbacks: MutationCallbacks) => {
      callbacks.onError?.(new Error('Duplication failed'), vars, undefined)
    })

    render(<BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    await openKebabAndClickDuplicate(user)

    expect(await screen.findByText('Failed to duplicate workflow')).toBeInTheDocument()
  })

  it('truncates long workflow names', async () => {
    const user = userEvent.setup()
    const longName = 'A'.repeat(250)

    const longWorkflow = { ...mockWorkflow, name: longName }

    render(<BuilderContent workflow={longWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    await openKebabAndClickDuplicate(user)

    await waitFor(() => expect(mockDuplicateMutate).toHaveBeenCalled())

    const callArg = mockDuplicateMutate.mock.calls[0]?.[0] as { body: { name: string } } | undefined
    expect(callArg).toBeDefined()
    expect(callArg?.body.name).toBeDefined()
    expect(callArg?.body.name.length).toBeLessThanOrEqual(255)
    expect(callArg?.body.name).toContain(' - duplicate-')
  })

  it('does not duplicate when already duplicating', async () => {
    const user = userEvent.setup()

    vi.mocked(workflowClient.useMutation).mockImplementation((method: string, path: string) => {
      if (method === 'post' && path === '/workflows') {
        return {
          mutate: mockDuplicateMutate,
          isPending: true,
        } as never
      }
      return {
        mutate: vi.fn(),
        isPending: false,
      } as never
    })

    render(<BuilderContent workflow={mockWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    await openKebabAndClickDuplicate(user)

    expect(mockDuplicateMutate).not.toHaveBeenCalled()
  })

  it('preserves workflow labels', async () => {
    const user = userEvent.setup()
    const labelsWorkflow = { ...mockWorkflow, labels: { env: 'prod', team: 'backend' } }

    render(<BuilderContent workflow={labelsWorkflow} isNew={false} workflowId="workflow-1" />, { wrapper })

    await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument())
    await openKebabAndClickDuplicate(user)

    await waitFor(() => expect(mockDuplicateMutate).toHaveBeenCalled())

    const callArg = mockDuplicateMutate.mock.calls[0]?.[0] as { body: { labels: Record<string, string> } } | undefined
    expect(callArg).toBeDefined()
    expect(callArg?.body.labels).toEqual({ env: 'prod', team: 'backend' })
  })
})
