import type { WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChildWorkflowSchema } from './useChildWorkflowSchema'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('../../../../client', () => ({ workflowFetchClient: { GET: mocks.get } }))

const childDefinition = {
  schema_version: '2.0.0',
  name: 'Child workflow',
  triggers: [
    { id: 'deploy', type: 'subworkflow_trigger', name: 'Deploy', parameters: {} },
    { id: 'validate', type: 'subworkflow_trigger', name: 'Validate', parameters: {} },
  ],
  nodes: [
    {
      id: 'deploy-script',
      name: 'Deploy application',
      type: 'script',
      parameters: { language: 'python', code: 'print("deployed")' },
    },
    {
      id: 'shared-script',
      name: 'Shared output',
      type: 'script',
      parameters: { language: 'python', code: 'print("shared")' },
      outputs: { image_tag: '${result.stdout_json.tag}' },
    },
    {
      id: 'validate-script',
      name: 'Validate application',
      type: 'script',
      parameters: { language: 'python', code: 'print("validated")' },
    },
  ],
  edges: [
    { from: 'deploy', to: 'deploy-script' },
    { from: 'deploy-script', to: 'shared-script' },
    { from: 'validate', to: 'validate-script' },
  ],
} satisfies WorkflowAPI.components['schemas']['WorkflowDefinition']

const invocationSchema = {
  workflow_id: 'child-workflow',
  published_version_id: 'published-v4',
  published_version: 4,
  is_eligible: true,
  triggers: [
    { trigger_node_id: 'deploy', name: 'Deploy', input_schema: {} },
    { trigger_node_id: 'validate', name: 'Validate', input_schema: {} },
  ],
} satisfies WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead']

const publishedVersion = {
  id: 'published-v4',
  workflow_id: 'child-workflow',
  version: 4,
  schema_version: '2.0.0',
  workflow_definition: childDefinition,
  status: 'published',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} satisfies WorkflowAPI.components['schemas']['WorkflowVersionRead']

const latestInvocationSchema = {
  ...invocationSchema,
  published_version_id: 'published-v5',
  published_version: 5,
} satisfies WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead']

const latestPublishedVersion = {
  ...publishedVersion,
  id: 'published-v5',
  version: 5,
} satisfies WorkflowAPI.components['schemas']['WorkflowVersionRead']

const workflowDetail = {
  id: 'child-workflow',
  name: 'Child workflow',
  current_version: 4,
  is_enabled: true,
  project_id: 'project-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  published_version_id: 'published-v4',
  published_version_number: 4,
  version: publishedVersion,
  published_step_metadata: {
    version_id: 'published-v4',
    version: 4,
    steps: childDefinition.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      output_schema:
        node.id === 'shared-script'
          ? {
              type: 'object',
              properties: {
                status: { type: 'string' },
                image_tag: {
                  description: 'Output produced by a configured mapping; its type is not statically known.',
                  'x-syntara-output-mapped': true,
                },
              },
            }
          : { type: 'object', properties: { stdout: { type: 'string' } } },
    })),
  },
} satisfies WorkflowAPI.components['schemas']['WorkflowDetailRead']

const latestWorkflowDetail = {
  ...workflowDetail,
  current_version: 5,
  published_version_id: 'published-v5',
  published_version_number: 5,
  version: latestPublishedVersion,
  published_step_metadata: {
    ...workflowDetail.published_step_metadata,
    version_id: 'published-v5',
    version: 5,
  },
} satisfies WorkflowAPI.components['schemas']['WorkflowDetailRead']

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useChildWorkflowSchema', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.get.mockImplementation((path: string) => {
      if (path.includes('invocation_schema')) {
        return Promise.resolve({ data: invocationSchema, response: new Response() })
      }
      if (path.includes('/versions/')) {
        return Promise.resolve({ data: publishedVersion, response: new Response() })
      }
      return Promise.resolve({ data: workflowDetail, response: new Response() })
    })
  })

  it('loads the published graph and scopes child steps to the selected trigger', async () => {
    const { result } = renderHook(
      () => useChildWorkflowSchema({ workflowId: 'child-workflow', triggerNodeId: 'deploy' }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.publishedVersionId).toBe('published-v4')
    expect(result.current.publishedVersion).toBe(4)
    expect(result.current.childSteps.map((step) => step.id)).toEqual(['shared-script'])
    expect(result.current.childSteps[0]?.outputSchema).toMatchObject({ type: 'object' })
    expect(result.current.childSteps[0]?.outputFields?.map((field) => field.name)).toEqual(['status', 'image_tag'])
    expect(result.current.childSteps[0]?.outputFields?.find((field) => field.name === 'image_tag')?.type).toBe(
      'unknown'
    )
    expect(mocks.get).toHaveBeenCalledWith('/workflows/{workflow_id}/versions/{version}', {
      params: { path: { workflow_id: 'child-workflow', version: 4 } },
    })
    expect(mocks.get).toHaveBeenCalledWith('/workflows/{workflow_id}', {
      params: { path: { workflow_id: 'child-workflow' } },
    })
  })

  it('requires a trigger selection when the child has multiple triggers', async () => {
    const { result } = renderHook(() => useChildWorkflowSchema({ workflowId: 'child-workflow', triggerNodeId: null }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.needsTriggerSelection).toBe(true)
    expect(result.current.childSteps).toEqual([])
  })

  it('refreshes the invocation schema and loads matching metadata after a republish race', async () => {
    let invocationSchemaCalls = 0
    mocks.get.mockImplementation((path: string, options?: { params?: { path?: { version?: number } } }) => {
      if (path.includes('invocation_schema')) {
        invocationSchemaCalls += 1
        return Promise.resolve({
          data: invocationSchemaCalls === 1 ? invocationSchema : latestInvocationSchema,
          response: new Response(),
        })
      }
      if (path.includes('/versions/')) {
        return Promise.resolve({
          data: options?.params?.path?.version === 5 ? latestPublishedVersion : publishedVersion,
          response: new Response(),
        })
      }
      return Promise.resolve({ data: latestWorkflowDetail, response: new Response() })
    })

    const { result } = renderHook(
      () => useChildWorkflowSchema({ workflowId: 'child-workflow', triggerNodeId: 'deploy' }),
      { wrapper: createWrapper() }
    )

    // Wait for initial load - child steps come from invocation schema output_schema
    await waitFor(() => expect(result.current.childSteps.length).toBeGreaterThan(0))

    act(() => result.current.retry())

    await waitFor(() => {
      expect(result.current.publishedVersionId).toBe('published-v5')
    })
    expect(invocationSchemaCalls).toBe(2)
    expect(mocks.get).toHaveBeenCalledWith('/workflows/{workflow_id}/versions/{version}', {
      params: { path: { workflow_id: 'child-workflow', version: 5 } },
    })
  })

  it('does not expose child details when invocation-schema access is denied', async () => {
    mocks.get.mockImplementation((_path: string, options: { params: { path: { workflow_id: string } } }) =>
      Promise.resolve({
        error: { detail: 'Forbidden' },
        response: new Response(null, { status: 403 }),
        options,
      })
    )

    const { result } = renderHook(() => useChildWorkflowSchema({ workflowId: 'private-child', triggerNodeId: null }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAccessDenied).toBe(true)
    expect(result.current.invocationSchema).toBeNull()
    expect(result.current.childSteps).toEqual([])
  })

  it('reports a missing published child schema as not found', async () => {
    mocks.get.mockImplementation(() =>
      Promise.resolve({
        error: { detail: 'Not Found' },
        response: new Response(null, { status: 404 }),
      })
    )

    const { result } = renderHook(
      () => useChildWorkflowSchema({ workflowId: 'unpublished-child', triggerNodeId: null }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isNotFound).toBe(true)
    expect(result.current.invocationSchema).toBeNull()
    expect(result.current.childSteps).toEqual([])
    expect(mocks.get).toHaveBeenCalledTimes(1)
  })
})
