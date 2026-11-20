import type { WorkflowAPI } from '@syntara/contracts'
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useOutputContractReview } from './useOutputContractReview'

type BreakingChangesResponse = WorkflowAPI.components['schemas']['BreakingChangesResponse']
type ReviewMutationRequest = {
  params: { path: { workflow_id: string } }
  body: { workflow_definition: Record<string, unknown> }
}
type ReviewMutationCallbacks = {
  onSuccess: (response: BreakingChangesResponse) => void
  onError: (error: unknown) => void
}
type ReviewMutation = (request: ReviewMutationRequest, callbacks: ReviewMutationCallbacks) => void
type UseMutation = (method: string, path: string) => { mutate: ReviewMutation; isPending: boolean }

const mocks = vi.hoisted(() => ({ mutate: vi.fn<ReviewMutation>(), useMutation: vi.fn<UseMutation>() }))

vi.mock('../../../client', () => ({
  workflowClient: { useMutation: mocks.useMutation },
}))

const response: WorkflowAPI.components['schemas']['BreakingChangesResponse'] = {
  has_breaking_changes: true,
  triggers: [
    {
      trigger_id: 'deploy',
      changes: [{ change_type: 'removed_output', field_path: 'release.url', description: 'Removed release URL' }],
    },
  ],
  has_contract_changes: true,
  contract_changes: [
    {
      trigger_id: 'deploy',
      changes: [{ change_type: 'removed_output', field_path: 'release.url', description: 'Removed release URL' }],
    },
  ],
  parent_workflows: [
    {
      workflow_id: 'parent-workflow',
      workflow_name: 'Parent workflow',
      workflow_version: 2,
      step_id: 'call_child',
    },
  ],
}

describe('useOutputContractReview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.useMutation.mockReturnValue({ mutate: mocks.mutate, isPending: false })
  })

  it('sends the candidate definition and exposes the contract review response', async () => {
    const workflowDefinition = { triggers: [{ id: 'deploy' }] }
    mocks.mutate.mockImplementation((_request, callbacks) => callbacks.onSuccess(response))
    const { result } = renderHook(() => useOutputContractReview('child-workflow'))
    const onError = vi.fn()
    let reviewResponse: WorkflowAPI.components['schemas']['BreakingChangesResponse'] | null = null

    await act(async () => {
      reviewResponse = await result.current.reviewOutputContract(workflowDefinition, onError)
    })

    expect(mocks.useMutation).toHaveBeenCalledWith(
      'post',
      '/workflows/{workflow_id}/check_subworkflow_output_contract_changes'
    )
    expect(mocks.mutate).toHaveBeenCalledTimes(1)
    expect(mocks.mutate.mock.calls.at(0)?.[0]).toEqual({
      params: { path: { workflow_id: 'child-workflow' } },
      body: { workflow_definition: workflowDefinition },
    })
    expect(reviewResponse).toEqual(response)
    expect(result.current.breakingChanges).toEqual(response.triggers)
    expect(result.current.contractChanges).toEqual(response.contract_changes)
    expect(result.current.parentWorkflows).toEqual(response.parent_workflows)
    expect(onError).not.toHaveBeenCalled()
  })

  it('reports request errors to the caller and resolves without a response', async () => {
    const requestError = new Error('Request failed')
    const onError = vi.fn()
    mocks.mutate.mockImplementation((_request, callbacks) => callbacks.onError(requestError))
    const { result } = renderHook(() => useOutputContractReview('child-workflow'))
    let reviewResponse: WorkflowAPI.components['schemas']['BreakingChangesResponse'] | null = null

    await act(async () => {
      reviewResponse = await result.current.reviewOutputContract({ triggers: [] }, onError)
    })

    expect(onError).toHaveBeenCalledWith(requestError)
    expect(reviewResponse).toBeNull()
    expect(result.current.breakingChanges).toEqual([])
    expect(result.current.contractChanges).toEqual([])
    expect(result.current.parentWorkflows).toEqual([])
  })

  it('clears previously reviewed changes', async () => {
    mocks.mutate.mockImplementation((_request, callbacks) => callbacks.onSuccess(response))
    const { result } = renderHook(() => useOutputContractReview('child-workflow'))

    await act(async () => {
      await result.current.reviewOutputContract({ triggers: [] }, vi.fn())
    })
    expect(result.current.contractChanges).toEqual(response.contract_changes)

    act(() => result.current.clearReview())

    expect(result.current.breakingChanges).toEqual([])
    expect(result.current.contractChanges).toEqual([])
    expect(result.current.parentWorkflows).toEqual([])
  })
})
