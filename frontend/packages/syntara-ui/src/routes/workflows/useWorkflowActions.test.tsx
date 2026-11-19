import type { WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { executionsFetchClient, workflowFetchClient } from '../../client'

import { useWorkflowActions } from './useWorkflowActions'

const publishedRequests = vi.hoisted(() => vi.fn())

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

vi.mock('../../providers/alerts', () => ({ useAlerts: () => ({ showError: vi.fn() }) }))

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
          mutate: vi.fn((_params: unknown, callbacks?: MutationCallbacks) => {
            // Simulate successful deletion
            callbacks?.onSuccess?.()
            callbacks?.onSettled?.()
          }),
          isPending,
        }
      }
      if (typeof path === 'string' && path.includes('/publish')) {
        // Publish mutation
        return {
          mutate: vi.fn((_params: unknown, callbacks?: MutationCallbacks) => {
            publishedRequests(_params)
            // Simulate successful publish
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
    vi.mocked(workflowFetchClient.GET)
      .mockReset()
      .mockResolvedValue({
        data: { kafka_subscription_sources: [], version: { version: 1, workflow_definition: {} } },
        response: new Response(),
      })
  })

  it('requires carry-forward before publishing the selected list workflow and version', async () => {
    const source = {
      trigger_node_id: 'subscribe',
      source_id: 'source-1',
      generation: 1,
      configuration_revision: 1,
      integration_id: 'integration-1',
      topic: 'orders',
      group_id: 'established-A',
      group_id_is_generated: false,
    }
    const definition = {
      triggers: [
        {
          id: 'subscribe',
          type: 'event_subscribe_trigger',
          parameters: {
            integration_id: 'integration-1',
            topic: 'orders',
            group_id: 'draft-B',
          },
        },
      ],
    }
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: { kafka_subscription_sources: [source], version: { version: 3, workflow_definition: definition } },
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
    result.current.handlePublishWorkflow(mockWorkflow({ id: 'selected-workflow', current_version: 3 }))
    await waitFor(() => expect(result.current.publication.groupConflicts).toHaveLength(1))
    expect(publishedRequests).not.toHaveBeenCalled()
    expect(workflowFetchClient.GET).toHaveBeenCalledWith('/workflows/{workflow_id}', {
      params: { path: { workflow_id: 'selected-workflow' } },
    })
    result.current.publication.confirmGroups()
    await waitFor(() =>
      expect(publishedRequests).toHaveBeenCalledWith(
        expect.objectContaining({
          params: { path: { workflow_id: 'selected-workflow', version: 3 } },
          body: {
            name: null,
            change_description: null,
            workflow_definition: {
              triggers: [
                {
                  ...definition.triggers[0],
                  parameters: { ...definition.triggers[0]?.parameters, group_id: 'established-A' },
                },
              ],
            },
          },
        })
      )
    )
    expect(definition.triggers[0]?.parameters.group_id).toBe('draft-B')
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
      result.current.handlePublishWorkflow(workflow)

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
      result.current.handlePublishWorkflow(workflow)

      await waitFor(() => {
        expect(mockShowSuccess).toHaveBeenCalledWith({
          title: 'Workflow published',
        })
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
