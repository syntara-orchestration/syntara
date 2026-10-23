import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { InvocationSchemaFetchError, useChildWorkflowSelector } from './useChildWorkflowSelector'

const mocks = vi.hoisted(() => ({
  invocationSchemaGet: vi.fn(),
  projectWorkflowsGet: vi.fn(),
  workflowQuery: vi.fn(),
}))

vi.mock('../../../client', () => ({
  workflowFetchClient: { GET: mocks.invocationSchemaGet },
  workflowClient: { useQuery: mocks.workflowQuery },
}))
vi.mock('../../access/accessClient', () => ({ accessFetchClient: { GET: mocks.projectWorkflowsGet } }))

const testWorkflows = [
  {
    id: 'workflow-1',
    name: 'Eligible workflow',
    current_version: 8,
    published_version_number: 4,
    is_enabled: true,
    project_id: 'project-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'workflow-2',
    name: 'No trigger workflow',
    current_version: 2,
    published_version_number: 2,
    is_enabled: true,
    project_id: 'project-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'workflow-3',
    name: 'Unpublished workflow',
    current_version: 1,
    published_version_number: null,
    is_enabled: true,
    project_id: 'project-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const nextPageWorkflow = {
  id: 'workflow-4',
  name: 'Eligible workflow on page two',
  current_version: 1,
  published_version_number: 1,
  is_enabled: true,
  project_id: 'project-1',
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useChildWorkflowSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.projectWorkflowsGet.mockImplementation(
      (_path: string, options: { params: { query: { cursor: string | null }; path: { project_id: string } } }) =>
        Promise.resolve({
          data:
            options.params.query.cursor === 'cursor-2'
              ? { resources: [nextPageWorkflow], next: null }
              : { resources: testWorkflows, next: 'cursor-2' },
        })
    )
    mocks.invocationSchemaGet.mockImplementation(
      (_path: string, options: { params: { path: { workflow_id: string } } }) => {
        const workflowId = options.params.path.workflow_id
        const isEligible = workflowId !== 'workflow-2'
        return Promise.resolve({
          data: {
            workflow_id: workflowId,
            published_version_id: `version-${workflowId}`,
            published_version: workflowId === 'workflow-4' ? 1 : 4,
            is_eligible: isEligible,
            triggers: isEligible
              ? [{ trigger_node_id: 'sub-trigger', name: 'Subworkflow Trigger', input_schema: {} }]
              : [],
          },
          response: new Response(),
        })
      }
    )
    mocks.workflowQuery.mockImplementation(
      (_method: string, _path: string, options: { params: { path: { workflow_id: string } } }) => ({
        data:
          options.params.path.workflow_id === 'workflow-private'
            ? {
                id: 'workflow-private',
                name: 'Selected workflow outside this page',
                published_version_number: 7,
                description: 'Selected workflow description',
              }
            : undefined,
        isError: false,
        refetch: vi.fn(),
      })
    )
  })

  it('filters by substring and lists only published workflows with eligible Subworkflow Triggers', async () => {
    const { result } = renderHook(
      () => useChildWorkflowSelector({ projectId: 'project-1', selectedWorkflowId: null }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.options).toHaveLength(1))

    expect(result.current.options[0]).toMatchObject({ value: 'workflow-1', label: 'Eligible workflow (v4)' })
    expect(mocks.projectWorkflowsGet).toHaveBeenCalledWith('/projects/{project_id}/workflows', {
      params: {
        path: { project_id: 'project-1' },
        query: {
          limit: 20,
          cursor: null,
          sort: 'name',
          include_total: false,
          is_enabled: true,
        },
      },
    })

    act(() => result.current.setSearchTerm('eligible'))
    await waitFor(() =>
      expect(mocks.projectWorkflowsGet).toHaveBeenCalledWith('/projects/{project_id}/workflows', {
        params: {
          path: { project_id: 'project-1' },
          query: {
            limit: 20,
            cursor: null,
            sort: 'name',
            include_total: false,
            is_enabled: true,
            'name[contains]': 'eligible',
          },
        },
      })
    )
  })

  it('reports project workflow permission failures and recovers on retry', async () => {
    mocks.projectWorkflowsGet
      .mockResolvedValueOnce({
        error: { detail: 'Forbidden' },
        response: new Response(null, { status: 403 }),
      })
      .mockResolvedValueOnce({ data: { resources: [testWorkflows[0]], next: null } })

    const { result } = renderHook(
      () => useChildWorkflowSelector({ projectId: 'project-1', selectedWorkflowId: null }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.hasError).toBe(true))
    expect(result.current.errorMessage).toBe('You do not have permission to view workflows in this project.')

    act(() => result.current.retryFailedLookups())
    await waitFor(() => expect(result.current.options).toHaveLength(1))
    expect(result.current.hasError).toBe(false)
  })

  it('loads additional workflow pages on demand', async () => {
    const { result } = renderHook(
      () => useChildWorkflowSelector({ projectId: 'project-1', selectedWorkflowId: null }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    act(() => result.current.loadMoreWorkflows())

    await waitFor(() => expect(result.current.options).toHaveLength(2))
    expect(mocks.projectWorkflowsGet).toHaveBeenCalledWith('/projects/{project_id}/workflows', {
      params: {
        path: { project_id: 'project-1' },
        query: {
          limit: 20,
          cursor: 'cursor-2',
          sort: 'name',
          include_total: false,
          is_enabled: true,
        },
      },
    })
    expect(result.current.options[1]).toMatchObject({
      value: 'workflow-4',
      label: 'Eligible workflow on page two (v1)',
    })
  })

  it('keeps the selected workflow name and trigger when it is outside the loaded pages', async () => {
    const { result } = renderHook(
      () => useChildWorkflowSelector({ projectId: 'project-1', selectedWorkflowId: 'workflow-private' }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.selectedOption?.value).toBe('workflow-private'))
    expect(result.current.selectedWorkflowLabel).toBe('Selected workflow outside this page (v7)')
    expect(result.current.selectedOption).toMatchObject({
      value: 'workflow-private',
      label: 'Selected workflow outside this page (v7)',
    })
    expect(mocks.invocationSchemaGet).toHaveBeenCalledWith('/workflows/{workflow_id}/invocation_schema', {
      params: { path: { workflow_id: 'workflow-private' } },
    })
  })

  it('preserves the HTTP status for authorization handling', async () => {
    mocks.invocationSchemaGet.mockImplementation(
      (_path: string, options: { params: { path: { workflow_id: string } } }) =>
        Promise.resolve({
          error: { detail: 'Forbidden' },
          response: new Response(null, { status: options.params.path.workflow_id === 'private' ? 403 : 404 }),
        })
    )

    const { result } = renderHook(
      () => useChildWorkflowSelector({ projectId: 'project-1', selectedWorkflowId: 'private' }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.selectedSchemaError).toBeInstanceOf(InvocationSchemaFetchError))
    expect(result.current.selectedSchemaError).toMatchObject({ status: 403 })
  })

  it('keeps verified workflows selectable when another invocation schema lookup is forbidden', async () => {
    mocks.invocationSchemaGet.mockImplementation(
      (_path: string, options: { params: { path: { workflow_id: string } } }) => {
        if (options.params.path.workflow_id === 'workflow-2') {
          return Promise.resolve({
            error: { detail: 'Forbidden' },
            response: new Response(null, { status: 403 }),
          })
        }
        return Promise.resolve({
          data: {
            workflow_id: options.params.path.workflow_id,
            published_version_id: `version-${options.params.path.workflow_id}`,
            published_version: 4,
            is_eligible: true,
            triggers: [{ trigger_node_id: 'sub-trigger', name: 'Subworkflow Trigger', input_schema: {} }],
          },
          response: new Response(),
        })
      }
    )

    const { result } = renderHook(
      () => useChildWorkflowSelector({ projectId: 'project-1', selectedWorkflowId: null }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.hasError).toBe(true))
    expect(result.current.errorMessage).toBe('Some workflows could not be checked because of permissions.')
    expect(result.current.options.map((option) => option.value)).toEqual(['workflow-1'])
  })
})
