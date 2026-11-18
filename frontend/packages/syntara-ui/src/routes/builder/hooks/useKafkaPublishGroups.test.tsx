import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { workflowFetchClient } from '../../../client'

import { useKafkaPublishGroups } from './useKafkaPublishGroups'

vi.mock('../../../client', () => ({ workflowFetchClient: { GET: vi.fn() } }))
const showError = vi.fn()
vi.mock('../../../providers/alerts', () => ({ useAlerts: () => ({ showError }) }))
const definition = {
  schema_version: '2.0.0',
  triggers: [
    {
      id: 'subscribe',
      type: 'event_subscribe_trigger',
      parameters: {
        integration_id: 'integration-1',
        topic: 'orders',
        group_id: 'draft-B',
        filter: { expression: '  true  ' },
      },
    },
  ],
  nodes: [{ id: 'step' }],
  edges: [],
}
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: { getState: () => ({ currentWorkflow: { triggers: definition.triggers } }) },
}))
const source = {
  trigger_node_id: 'subscribe',
  source_id: 'source-1',
  generation: 1,
  configuration_revision: 1,
  group_id_is_generated: false,
  integration_id: 'integration-1',
  topic: 'orders',
  group_id: 'published-A',
}
function response(sources = [source], target: Record<string, unknown> = definition) {
  return {
    data: { kafka_subscription_sources: sources, version: { version: 3, workflow_definition: target } },
    response: new Response(),
  }
}
function setup(dirty = false) {
  const submit = vi.fn<Parameters<typeof useKafkaPublishGroups>[0]['submit']>()
  const getDefinition = vi.fn(() => (dirty ? definition : undefined))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  function wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return {
    ...renderHook(() => useKafkaPublishGroups({ workflowId: 'workflow-1', currentVersion: 3, getDefinition, submit }), {
      wrapper,
    }),
    submit,
  }
}
beforeEach(() => {
  vi.mocked(workflowFetchClient.GET).mockReset()
  showError.mockClear()
})

describe('Kafka publication group reconciliation', () => {
  it.each([false, true])(
    'checks a stale group without reopening the form, then carries it forward only after confirmation (dirty=%s)',
    async (dirty) => {
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(response())
      const { result, submit } = setup(dirty)
      const settled = vi.fn()
      act(() => result.current.publish('Release', 'Description', settled, { expectedVersionOverride: 3 }))
      await waitFor(() => expect(result.current.groupConflicts).toHaveLength(1))
      expect(submit).not.toHaveBeenCalled()
      expect(definition.triggers[0]?.parameters.group_id).toBe('draft-B')
      expect(settled).toHaveBeenCalledOnce()
      act(() => result.current.confirmGroups())
      await waitFor(() => expect(submit).toHaveBeenCalledOnce())
      expect(workflowFetchClient.GET).toHaveBeenCalledTimes(2)
      expect(submit).toHaveBeenCalledWith('Release', 'Description', undefined, {
        expectedVersionOverride: 3,
        workflowDefinition: {
          ...definition,
          triggers: [
            {
              ...definition.triggers[0],
              parameters: { ...definition.triggers[0]?.parameters, group_id: 'published-A' },
            },
          ],
        },
      })
    }
  )

  it('leaves the draft unchanged when the carry-forward prompt is cancelled', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(response())
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(result.current.groupConflicts).toHaveLength(1))
    act(() => result.current.cancelGroups())
    expect(result.current.groupConflicts).toBeUndefined()
    expect(submit).not.toHaveBeenCalled()
    expect(definition.triggers[0]?.parameters.group_id).toBe('draft-B')
  })

  it('requires renewed confirmation when another publication changes the source generation', async () => {
    vi.mocked(workflowFetchClient.GET)
      .mockResolvedValueOnce(response())
      .mockResolvedValue(response([{ ...source, source_id: 'source-2', generation: 2, group_id: 'published-C' }]))
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(result.current.groupConflicts?.[0]?.source.group_id).toBe('published-A'))
    act(() => result.current.confirmGroups())
    await waitFor(() => expect(result.current.groupConflicts?.[0]?.source.group_id).toBe('published-C'))
    expect(submit).not.toHaveBeenCalled()
    act(() => result.current.confirmGroups())
    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(submit.mock.calls[0]?.[3]?.workflowDefinition).toMatchObject({
      triggers: [{ parameters: { group_id: 'published-C' } }],
    })
  })

  it('does not publish after cancellation while confirmation is refreshing the source', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(response())
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(result.current.groupConflicts).toHaveLength(1))
    let finish: (() => void) | undefined
    vi.mocked(workflowFetchClient.GET).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = () => resolve(response())
        })
    )
    act(() => result.current.confirmGroups())
    await waitFor(() => expect(result.current.isCheckingGroups).toBe(true))
    act(() => result.current.cancelGroups())
    await act(async () => {
      finish?.()
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.isCheckingGroups).toBe(false))
    expect(result.current.groupConflicts).toBeUndefined()
    expect(submit).not.toHaveBeenCalled()
  })

  it('does not replace a group for a different Integration or topic', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(response([{ ...source, topic: 'different-source' }]))
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(submit.mock.calls[0]?.[3]?.workflowDefinition).toBeUndefined()
    expect(result.current.groupConflicts).toBeUndefined()
  })

  it('materializes an omitted effective group without erasing its portable identity', async () => {
    const noGroup = {
      ...definition,
      triggers: [{ ...definition.triggers[0], parameters: { ...definition.triggers[0]?.parameters, group_id: '' } }],
    }
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(response([source], noGroup))
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(result.current.groupConflicts).toBeUndefined()
    expect(submit.mock.calls[0]?.[3]?.workflowDefinition).toMatchObject({
      triggers: [{ parameters: { group_id: 'published-A' } }],
    })
  })

  it('checks the selected saved version even when the editor contains an unsaved draft', async () => {
    vi.mocked(workflowFetchClient.GET)
      .mockResolvedValueOnce(response())
      .mockResolvedValueOnce({ data: { version: 1, workflow_definition: definition }, response: new Response() })
    const { result, submit } = setup(true)
    act(() => result.current.publish(undefined, undefined, undefined, { versionOverride: 1 }))
    await waitFor(() => expect(result.current.groupConflicts).toHaveLength(1))
    expect(workflowFetchClient.GET).toHaveBeenLastCalledWith('/workflows/{workflow_id}/versions/{version}', {
      params: { path: { workflow_id: 'workflow-1', version: 1 } },
    })
    expect(submit).not.toHaveBeenCalled()
  })

  it('does not publish when projection lookup fails', async () => {
    vi.mocked(workflowFetchClient.GET).mockRejectedValue(new Error('Unavailable'))
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(showError).toHaveBeenCalled())
    expect(submit).not.toHaveBeenCalled()
  })
})

describe('automatic consumer groups', () => {
  it.each([undefined, null])('preserves automatic mode (%s) without a publish override', async (groupId) => {
    const automatic = { ...source, group_id: 'syntara.source-runtime-id', group_id_is_generated: true }
    const target = {
      ...definition,
      triggers: [
        { ...definition.triggers[0], parameters: { ...definition.triggers[0]?.parameters, group_id: groupId } },
      ],
    }
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(response([automatic], target))
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(submit.mock.calls[0]?.[3]?.workflowDefinition).toBeUndefined()
    expect(target.triggers[0]?.parameters.group_id).toBe(groupId)
  })

  it('carries a stale custom override back to automatic mode after confirmation', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(response([{ ...source, group_id_is_generated: true }]))
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(result.current.groupConflicts).toHaveLength(1))
    act(() => result.current.confirmGroups())
    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    expect(submit.mock.calls[0]?.[3]?.workflowDefinition).toMatchObject({
      triggers: [{ parameters: { group_id: null } }],
    })
  })

  it('does not publish after dismissing the initial dialog while the lookup is pending', async () => {
    let finish: (() => void) | undefined
    vi.mocked(workflowFetchClient.GET).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = () => resolve(response([], definition))
        })
    )
    const { result, submit } = setup()
    act(() => result.current.publish())
    await waitFor(() => expect(result.current.isCheckingGroups).toBe(true))
    act(() => result.current.cancelGroups())
    await act(async () => {
      finish?.()
      await Promise.resolve()
    })
    expect(submit).not.toHaveBeenCalled()
    expect(result.current.groupConflicts).toBeUndefined()
  })
})
