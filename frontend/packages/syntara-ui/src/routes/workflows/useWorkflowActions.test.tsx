import type { WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { executionsFetchClient, workflowFetchClient } from '../../client'

import { useWorkflowActions } from './useWorkflowActions'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

// Helper to create mock workflow objects for testing
function mockWorkflow(overrides: Partial<Workflow> = {}): Workflow {
  return {
    id: 'wf-1',
    name: 'Test Workflow',
    description: null,
    labels: {},
    current_version: 1,
    is_builtin: false,
    is_enabled: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    created_by: { id: 'u-1', name: 'test-user', type: 'user' },
    project_id: 'proj-1',
    ...overrides,
  }
}

type MutationCallbacks = {
  onSuccess?: (data?: unknown) => void
  onError?: (error?: unknown) => void
  onSettled?: () => void
}

const mocks = vi.hoisted(() => ({ publishParams: vi.fn() }))
// Shared, test-controllable publish behavior for the trigger-removal 409 path.
const publishMock = vi.hoisted(() => ({ simulate409: false, confirmCalls: [] as boolean[] }))

// Shared, test-controllable delete behavior for the referenced-parents 409 path.
const deleteMock = vi.hoisted((): { simulate409: boolean; confirmCalls: boolean[]; retryError: unknown } => ({
  simulate409: false,
  confirmCalls: [],
  retryError: null,
}))

// Mock the API clients
vi.mock('../../client', () => ({
  executionsClient: {
    useMutation: vi.fn(() => ({
      mutate: vi.fn((_params: unknown, callbacks?: MutationCallbacks) => {
        // Simulate successful execution
        callbacks?.onSuccess?.({ id: 'exec-123' })
      }),
      isPending: false,
    })),
  },
  executionsFetchClient: {
    POST: vi.fn(),
  },
  workflowFetchClient: {
    GET: vi.fn(),
  },
  workflowClient: {
    useMutation: vi.fn((_method: unknown, path: unknown) => {
      const isPending = false
      if (path === '/workflows/{workflow_id}') {
        // Delete mutation
        return {
          mutate: vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
            const confirm = (params as { params?: { query?: { confirm?: boolean } } })?.params?.query?.confirm === true
            deleteMock.confirmCalls.push(confirm)
            // Referenced-by-published-parents 409: an unconfirmed delete is rejected until confirm=true.
            if (deleteMock.simulate409 && !confirm) {
              callbacks?.onError?.({
                cause: { code: 'WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED', referencing_count: 3 },
              })
              callbacks?.onSettled?.()
              return
            }
            if (confirm && deleteMock.retryError) {
              callbacks?.onError?.(deleteMock.retryError)
              callbacks?.onSettled?.()
              return
            }
            callbacks?.onSuccess?.()
            callbacks?.onSettled?.()
          }),
          isPending,
        }
      }
      if (typeof path === 'string' && path.includes('/publish')) {
        // Publish mutation
        return {
          mutate: vi.fn((params: unknown, callbacks?: MutationCallbacks) => {
            mocks.publishParams(params)
            const confirm = (params as { params?: { query?: { confirm?: boolean } } })?.params?.query?.confirm === true
            publishMock.confirmCalls.push(confirm)
            // Trigger-removal 409: an unconfirmed publish is rejected until confirm=true.
            if (publishMock.simulate409 && !confirm) {
              callbacks?.onError?.({
                cause: { code: 'WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED', affected_count: 2 },
              })
              callbacks?.onSettled?.()
              return
            }
            // Simulate successful publish.
            callbacks?.onSuccess?.()
            callbacks?.onSettled?.()
          }),
          isPending,
        }
      }
      // Unpublish mutation
      return {
        mutate: vi.fn((_params: unknown, callbacks?: MutationCallbacks) => {
          // Simulate successful unpublish
          callbacks?.onSuccess?.()
          callbacks?.onSettled?.()
        }),
        isPending: false,
      }
    }),
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useWorkflowActions', () => {
  const mockShowSuccess = vi.fn()
  const mockShowError = vi.fn()
  const mockOnNavigate = vi.fn()
  const mockOnRefetch = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(executionsFetchClient.POST).mockReset()
    vi.mocked(workflowFetchClient.GET).mockReset()
    publishMock.simulate409 = false
    publishMock.confirmCalls = []
    deleteMock.simulate409 = false
    deleteMock.confirmCalls = []
    deleteMock.retryError = null
  })

  describe('publish trigger-removal confirmation (list page)', () => {
    it('opens the confirm dialog on a trigger-removal 409 and republishes with confirm=true', async () => {
      publishMock.simulate409 = true
      const user = userEvent.setup()

      function Harness() {
        const actions = useWorkflowActions({
          showSuccess: mockShowSuccess,
          showError: mockShowError,
          onNavigate: mockOnNavigate,
          onRefetch: mockOnRefetch,
        })
        return (
          <>
            <button type="button" onClick={() => actions.handlePublishWorkflow(mockWorkflow())}>
              do-publish
            </button>
            {actions.triggerRemovalConfirmDialog}
          </>
        )
      }

      render(<Harness />, { wrapper: createWrapper() })
      await user.click(screen.getByRole('button', { name: 'do-publish' }))

      // First publish (confirm=false) returns the 409 -> confirmation dialog, no generic error yet.
      const confirmButton = await screen.findByRole('button', { name: 'Publish anyway' })
      expect(mockShowError).not.toHaveBeenCalled()

      await user.click(confirmButton)

      await waitFor(() =>
        expect(mockShowSuccess).toHaveBeenCalledWith(expect.objectContaining({ title: 'Workflow published' }))
      )
      expect(publishMock.confirmCalls).toEqual([false, true])
    })
  })

  describe('referenced delete confirmation (list page)', () => {
    it('opens the confirm dialog on a referenced 409 and re-deletes with confirm=true', async () => {
      deleteMock.simulate409 = true
      const user = userEvent.setup()

      function Harness() {
        const actions = useWorkflowActions({
          showSuccess: mockShowSuccess,
          showError: mockShowError,
          onNavigate: mockOnNavigate,
          onRefetch: mockOnRefetch,
        })
        return (
          <>
            <button type="button" onClick={() => actions.handleDeleteWorkflow(mockWorkflow())}>
              do-delete
            </button>
            {actions.referencedDeleteConfirmDialog}
          </>
        )
      }

      render(<Harness />, { wrapper: createWrapper() })
      await user.click(screen.getByRole('button', { name: 'do-delete' }))

      // First delete (confirm=false) returns the 409 -> confirmation dialog, no generic error yet.
      const confirmButton = await screen.findByRole('button', { name: 'Delete anyway' })
      expect(mockShowError).not.toHaveBeenCalled()

      await user.click(confirmButton)

      await waitFor(() =>
        expect(mockShowSuccess).toHaveBeenCalledWith(expect.objectContaining({ title: 'Workflow deleted' }))
      )
      expect(deleteMock.confirmCalls).toEqual([false, true])
    })

    it('cancelling the dependency dialog issues no confirmed DELETE (sequence stays [false])', async () => {
      deleteMock.simulate409 = true
      const user = userEvent.setup()

      function Harness() {
        const actions = useWorkflowActions({
          showSuccess: mockShowSuccess,
          showError: mockShowError,
          onNavigate: mockOnNavigate,
          onRefetch: mockOnRefetch,
        })
        return (
          <>
            <button type="button" onClick={() => actions.handleDeleteWorkflow(mockWorkflow())}>
              do-delete
            </button>
            {actions.referencedDeleteConfirmDialog}
          </>
        )
      }

      render(<Harness />, { wrapper: createWrapper() })
      await user.click(screen.getByRole('button', { name: 'do-delete' }))
      await screen.findByRole('button', { name: 'Delete anyway' })

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      // Cancel must never issue a confirmed DELETE: the request sequence stays [false].
      expect(deleteMock.confirmCalls).toEqual([false])
      expect(mockShowSuccess).not.toHaveBeenCalled()
      await waitFor(() => expect(screen.queryByRole('button', { name: 'Delete anyway' })).not.toBeInTheDocument())
    })

    it('onDeleteSettled from the initial 409 does not clear the dependency confirmation', async () => {
      deleteMock.simulate409 = true
      const onDeleteSettled = vi.fn()
      const user = userEvent.setup()

      function Harness() {
        const actions = useWorkflowActions({
          showSuccess: mockShowSuccess,
          showError: mockShowError,
          onNavigate: mockOnNavigate,
          onRefetch: mockOnRefetch,
          onDeleteSettled,
        })
        return (
          <>
            <button type="button" onClick={() => actions.handleDeleteWorkflow(mockWorkflow())}>
              do-delete
            </button>
            {actions.referencedDeleteConfirmDialog}
          </>
        )
      }

      render(<Harness />, { wrapper: createWrapper() })
      await user.click(screen.getByRole('button', { name: 'do-delete' }))

      // onDeleteSettled (which closes the original delete dialog) fires on the 409, but the
      // dependency confirmation stays open and functional.
      await waitFor(() => expect(onDeleteSettled).toHaveBeenCalledTimes(1))
      const confirmButton = await screen.findByRole('button', { name: 'Delete anyway' })
      await user.click(confirmButton)

      await waitFor(() =>
        expect(mockShowSuccess).toHaveBeenCalledWith(expect.objectContaining({ title: 'Workflow deleted' }))
      )
      expect(deleteMock.confirmCalls).toEqual([false, true])
      expect(onDeleteSettled).toHaveBeenCalledTimes(2)
    })

    it('surfaces an unrelated error when the confirmed retry fails, with no success and no further retry', async () => {
      deleteMock.simulate409 = true
      deleteMock.retryError = { cause: { code: 'WORKFLOW_HAS_ACTIVE_EXECUTIONS' }, message: 'has active executions' }
      const user = userEvent.setup()

      function Harness() {
        const actions = useWorkflowActions({
          showSuccess: mockShowSuccess,
          showError: mockShowError,
          onNavigate: mockOnNavigate,
          onRefetch: mockOnRefetch,
        })
        return (
          <>
            <button type="button" onClick={() => actions.handleDeleteWorkflow(mockWorkflow())}>
              do-delete
            </button>
            {actions.referencedDeleteConfirmDialog}
          </>
        )
      }

      render(<Harness />, { wrapper: createWrapper() })
      await user.click(screen.getByRole('button', { name: 'do-delete' }))
      await user.click(await screen.findByRole('button', { name: 'Delete anyway' }))

      await waitFor(() =>
        expect(mockShowError).toHaveBeenCalledWith(expect.objectContaining({ title: 'Failed to delete workflow' }))
      )
      expect(mockShowSuccess).not.toHaveBeenCalled()
      // Confirmed once (true); the failed retry is surfaced, not retried again.
      expect(deleteMock.confirmCalls).toEqual([false, true])
      expect(screen.queryByRole('button', { name: 'Delete anyway' })).not.toBeInTheDocument()
    })
  })

  describe('onSettled callbacks', () => {
    it('calls onDeleteSettled when delete mutation completes', async () => {
      const mockOnDeleteSettled = vi.fn()
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
            onDeleteSettled: mockOnDeleteSettled,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow()
      result.current.handleDeleteWorkflow(workflow)

      await waitFor(() => {
        expect(mockOnDeleteSettled).toHaveBeenCalledTimes(1)
      })
    })

    it('calls onPublishSettled when publish mutation completes', async () => {
      const mockOnPublishSettled = vi.fn()
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
            onPublishSettled: mockOnPublishSettled,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow()
      result.current.handlePublishWorkflow(workflow, 1)

      await waitFor(() => {
        expect(mockOnPublishSettled).toHaveBeenCalledTimes(1)
      })
    })

    it('calls onUnpublishSettled when unpublish mutation completes', async () => {
      const mockOnUnpublishSettled = vi.fn()
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
            onUnpublishSettled: mockOnUnpublishSettled,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow()
      result.current.handleUnpublishWorkflow(workflow)

      await waitFor(() => {
        expect(mockOnUnpublishSettled).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('success messages', () => {
    it('shows correct delete success message', async () => {
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow({ name: 'My Workflow' })
      result.current.handleDeleteWorkflow(workflow)

      await waitFor(() => {
        expect(mockShowSuccess).toHaveBeenCalledWith({
          title: 'Workflow deleted',
          description: 'Workflow "My Workflow" has been deleted.',
        })
      })
    })

    it('shows correct publish success message', async () => {
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow({ name: 'My Workflow' })
      result.current.handlePublishWorkflow(workflow, 1)

      await waitFor(() => {
        expect(mockShowSuccess).toHaveBeenCalledWith({
          title: 'Workflow published',
        })
      })
    })

    it('publishes the explicitly reviewed version instead of the workflow row version', async () => {
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow({ current_version: 8 })
      result.current.handlePublishWorkflow(workflow, 5, 'Reviewed version', 'Reviewed description')

      await waitFor(() => expect(mocks.publishParams).toHaveBeenCalledOnce())
      expect(mocks.publishParams).toHaveBeenCalledWith({
        params: { path: { workflow_id: 'wf-1', version: 5 }, query: { confirm: false } },
        body: { name: 'Reviewed version', change_description: 'Reviewed description' },
      })
    })

    it('publishes the version whose contract was reviewed', async () => {
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow({ current_version: 8 })
      result.current.handlePublishWorkflow(workflow, 5, 'Reviewed version', 'Description')

      await waitFor(() => expect(mocks.publishParams).toHaveBeenCalledOnce())
      expect(mocks.publishParams).toHaveBeenCalledWith({
        params: { path: { workflow_id: 'wf-1', version: 5 }, query: { confirm: false } },
        body: { name: 'Reviewed version', change_description: 'Description' },
      })
    })

    it('shows correct unpublish success message', async () => {
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow({ name: 'My Workflow' })
      result.current.handleUnpublishWorkflow(workflow)

      await waitFor(() => {
        expect(mockShowSuccess).toHaveBeenCalledWith({
          title: 'Workflow unpublished',
        })
      })
    })
  })

  describe('refetch behavior', () => {
    it('calls onRefetch after successful delete', async () => {
      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      const workflow = mockWorkflow({ name: 'Test' })
      result.current.handleDeleteWorkflow(workflow)

      await waitFor(() => {
        expect(mockOnRefetch).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('handleRunWorkflow', () => {
    it('posts collected input_data when triggerNodeId is provided', async () => {
      vi.mocked(executionsFetchClient.POST).mockResolvedValue({
        data: { id: 'exec-1' },
        error: undefined,
      })

      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      await result.current.handleRunWorkflow(mockWorkflow(), { version: '1.2.3' }, 'trigger-1')

      expect(executionsFetchClient.POST).toHaveBeenCalledWith('/executions', {
        body: {
          workflow_id: 'wf-1',
          input_data: { version: '1.2.3' },
          trigger_node_id: 'trigger-1',
          use_published: true,
        },
      })
      expect(mockOnNavigate).toHaveBeenCalledWith('/executions/exec-1')
      expect(workflowFetchClient.GET).not.toHaveBeenCalled()
    })

    it('resolves the trigger when triggerNodeId is omitted', async () => {
      vi.mocked(workflowFetchClient.GET).mockResolvedValue({
        data: {
          id: 'wf-1',
          current_version: 1,
          published_version_number: 1,
          version: {
            workflow_definition: {
              triggers: [{ id: 'resolved-trigger', name: 'Manual Trigger', parameters: {} }],
            },
          },
        },
        error: undefined,
        response: new Response(),
      })
      vi.mocked(executionsFetchClient.POST).mockResolvedValue({
        data: { id: 'exec-2' },
        error: undefined,
      })

      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      await result.current.handleRunWorkflow(mockWorkflow())

      expect(executionsFetchClient.POST).toHaveBeenCalledWith('/executions', {
        body: {
          workflow_id: 'wf-1',
          input_data: {},
          trigger_node_id: 'resolved-trigger',
          use_published: true,
        },
      })
    })

    it('shows an error when the workflow has no triggers', async () => {
      vi.mocked(workflowFetchClient.GET).mockResolvedValue({
        data: {
          id: 'wf-1',
          current_version: 1,
          published_version_number: 1,
          version: { workflow_definition: { triggers: [] } },
        },
        error: undefined,
        response: new Response(),
      })

      const { result } = renderHook(
        () =>
          useWorkflowActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onNavigate: mockOnNavigate,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: createWrapper() }
      )

      await result.current.handleRunWorkflow(mockWorkflow())

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Cannot run workflow',
        description: 'Workflow has no triggers configured',
      })
      expect(executionsFetchClient.POST).not.toHaveBeenCalled()
    })
  })
})
