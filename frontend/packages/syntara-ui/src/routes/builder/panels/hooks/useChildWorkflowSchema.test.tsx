import type { WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChildWorkflowSchema } from './useChildWorkflowSchema'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('../../../../client', () => ({ workflowFetchClient: { GET: mocks.get } }))

const deployTrigger: WorkflowAPI.components['schemas']['WorkflowInvocationTriggerSchema'] = {
  trigger_node_id: 'deploy',
  name: 'Deploy',
  input_schema: {},
  output_schema: {
    type: 'object',
    properties: {
      status: { type: 'string', description: 'Deployment status' },
      image_tag: { type: 'string', description: 'Published image tag' },
    },
  },
}

const validateTrigger: WorkflowAPI.components['schemas']['WorkflowInvocationTriggerSchema'] = {
  trigger_node_id: 'validate',
  name: 'Validate',
  input_schema: {},
  output_schema: { type: 'object', properties: { validation_status: { type: 'string' } } },
}

const invocationSchema: WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead'] = {
  workflow_id: 'child-workflow',
  published_version_id: 'published-v4',
  published_version: 4,
  is_eligible: true,
  triggers: [deployTrigger, validateTrigger],
}

const latestInvocationSchema: WorkflowAPI.components['schemas']['WorkflowInvocationSchemaRead'] = {
  ...invocationSchema,
  published_version_id: 'published-v5',
  published_version: 5,
  triggers: [
    {
      ...deployTrigger,
      output_schema: {
        type: 'object',
        properties: { release_tag: { type: 'string', description: 'Published release tag' } },
      },
    },
    validateTrigger,
  ],
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useChildWorkflowSchema', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.get.mockResolvedValue({ data: invocationSchema, response: new Response() })
  })

  it('uses the invocation schema to expose the selected trigger’s declared outputs', async () => {
    const { result } = renderHook(
      () => useChildWorkflowSchema({ workflowId: 'child-workflow', triggerNodeId: 'deploy' }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.publishedVersionId).toBe('published-v4')
    expect(result.current.publishedVersion).toBe(4)
    expect(result.current.childSteps.map((step) => step.id)).toEqual(['__declared_outputs__'])
    expect(result.current.childSteps[0]?.outputSchema).toMatchObject({ type: 'object' })
    expect(result.current.childSteps[0]?.outputFields?.map((field) => field.name)).toEqual(['status', 'image_tag'])
    expect(result.current.childSteps[0]?.outputFields?.find((field) => field.name === 'image_tag')?.type).toBe('string')
    expect(mocks.get).toHaveBeenCalledTimes(1)
    expect(mocks.get).toHaveBeenCalledWith('/workflows/{workflow_id}/invocation_schema', {
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

  it('reports a requested trigger as unavailable when it is not in the invocation schema', async () => {
    mocks.get.mockResolvedValue({
      data: { ...invocationSchema, triggers: [validateTrigger] },
      response: new Response(),
    })

    const { result } = renderHook(
      () => useChildWorkflowSchema({ workflowId: 'child-workflow', triggerNodeId: 'removed-trigger' }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.selectedTriggerNodeId).toBeNull()
    expect(result.current.isTriggerUnavailable).toBe(true)
    expect(result.current.childSteps).toEqual([])
  })

  it('refreshes the invocation schema and its output contract on retry', async () => {
    let invocationSchemaCalls = 0
    mocks.get.mockImplementation(() => {
      invocationSchemaCalls += 1
      return Promise.resolve({
        data: invocationSchemaCalls === 1 ? invocationSchema : latestInvocationSchema,
        response: new Response(),
      })
    })

    const { result } = renderHook(
      () => useChildWorkflowSchema({ workflowId: 'child-workflow', triggerNodeId: 'deploy' }),
      { wrapper: createWrapper() }
    )

    await waitFor(() =>
      expect(result.current.childSteps[0]?.outputFields?.map((field) => field.name)).toEqual(['status', 'image_tag'])
    )

    act(() => result.current.retry())

    await waitFor(() => {
      expect(result.current.publishedVersionId).toBe('published-v5')
      expect(result.current.childSteps[0]?.outputFields?.map((field) => field.name)).toEqual(['release_tag'])
    })
    expect(invocationSchemaCalls).toBe(2)
  })

  it('does not expose child outputs when invocation-schema access is denied', async () => {
    mocks.get.mockResolvedValue({
      error: { detail: 'Forbidden' },
      response: new Response(null, { status: 403 }),
    })

    const { result } = renderHook(() => useChildWorkflowSchema({ workflowId: 'private-child', triggerNodeId: null }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAccessDenied).toBe(true)
    expect(result.current.invocationSchema).toBeNull()
    expect(result.current.childSteps).toEqual([])
  })

  it('reports a missing published child schema as not found', async () => {
    mocks.get.mockResolvedValue({
      error: { detail: 'Not Found' },
      response: new Response(null, { status: 404 }),
    })

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
