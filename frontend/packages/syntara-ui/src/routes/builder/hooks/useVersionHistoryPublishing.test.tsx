import type { WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useVersionHistoryPublishing } from './useVersionHistoryPublishing'

const mocks = vi.hoisted(() => ({
  clearReview: vi.fn(),
  mutate: vi.fn(),
  review: vi.fn(),
  showError: vi.fn(),
  showSuccess: vi.fn(),
}))

vi.mock('../../../client', () => ({
  workflowClient: {
    useMutation: () => ({ mutate: mocks.mutate, isPending: false }),
  },
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showError: mocks.showError, showSuccess: mocks.showSuccess }),
}))

vi.mock('./useOutputContractReview', () => ({
  useOutputContractReview: () => ({
    breakingChanges: [],
    contractChanges: [],
    parentWorkflows: [],
    isChecking: false,
    clearReview: mocks.clearReview,
    reviewOutputContract: mocks.review,
  }),
}))

const workflowDefinition = { schema_version: '2.0.0', name: 'child-v2' }
const versions: WorkflowAPI.components['schemas']['WorkflowVersionRead'][] = [
  {
    id: 'version-2-id',
    workflow_id: 'workflow-1',
    version: 2,
    schema_version: '2.0.0',
    workflow_definition: workflowDefinition,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

function reviewResponse(
  changes: Partial<WorkflowAPI.components['schemas']['BreakingChangesResponse']> = {}
): WorkflowAPI.components['schemas']['BreakingChangesResponse'] {
  return {
    has_breaking_changes: false,
    triggers: [],
    has_contract_changes: false,
    contract_changes: [],
    parent_workflows: [],
    ...changes,
  }
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useVersionHistoryPublishing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.review.mockResolvedValue(reviewResponse())
  })

  it('reviews the selected version without publishing when the dialog opens', async () => {
    const { result } = renderHook(
      () =>
        useVersionHistoryPublishing({
          workflowId: 'workflow-1',
          versions,
          refetchVersions: vi.fn().mockResolvedValue(undefined),
        }),
      { wrapper: createWrapper() }
    )

    act(() => result.current.reviewVersionForPublish(2))

    await waitFor(() => expect(result.current.reviewedPublishVersion).toBe(2))
    expect(mocks.review).toHaveBeenCalledWith(workflowDefinition, expect.any(Function))
    expect(mocks.mutate).not.toHaveBeenCalled()
  })

  it('publishes the reviewed version without repeating the contract request', async () => {
    const refetchVersions = vi.fn().mockResolvedValue(undefined)
    const onSettled = vi.fn()
    const { result } = renderHook(
      () =>
        useVersionHistoryPublishing({
          workflowId: 'workflow-1',
          versions,
          refetchVersions,
        }),
      { wrapper: createWrapper() }
    )

    act(() => result.current.reviewVersionForPublish(2))
    await waitFor(() => expect(result.current.reviewedPublishVersion).toBe(2))

    act(() => result.current.publishVersion(2, 'Release 2', 'Publish reviewed contract', onSettled))

    expect(mocks.review).toHaveBeenCalledOnce()
    expect(mocks.mutate).toHaveBeenCalledWith(
      {
        params: { path: { workflow_id: 'workflow-1', version: 2 } },
        body: { name: 'Release 2', change_description: 'Publish reviewed contract' },
      },
      expect.objectContaining({ onSettled })
    )
  })

  it('waits for author confirmation when the reviewed contract changed', async () => {
    mocks.review.mockResolvedValue(
      reviewResponse({
        has_breaking_changes: true,
        has_contract_changes: true,
        triggers: [{ trigger_id: 'child-entry', trigger_name: 'Child entry', changes: [] }],
      })
    )
    const { result } = renderHook(
      () =>
        useVersionHistoryPublishing({
          workflowId: 'workflow-1',
          versions,
          refetchVersions: vi.fn().mockResolvedValue(undefined),
        }),
      { wrapper: createWrapper() }
    )

    act(() => result.current.reviewVersionForPublish(2))
    await waitFor(() => expect(result.current.reviewedPublishVersion).toBe(2))
    act(() => result.current.publishVersion(2, 'Release 2', 'Breaking change'))
    expect(mocks.mutate).not.toHaveBeenCalled()

    act(() => result.current.confirmPublishVersion('Release 2', 'Breaking change'))
    expect(mocks.mutate).toHaveBeenCalledOnce()
  })

  it('does not restore a review after cancellation while the request is pending', async () => {
    let resolveReview: ((response: WorkflowAPI.components['schemas']['BreakingChangesResponse']) => void) | undefined
    mocks.review.mockReturnValue(
      new Promise<WorkflowAPI.components['schemas']['BreakingChangesResponse']>((resolve) => {
        resolveReview = resolve
      })
    )
    const { result } = renderHook(
      () =>
        useVersionHistoryPublishing({
          workflowId: 'workflow-1',
          versions,
          refetchVersions: vi.fn().mockResolvedValue(undefined),
        }),
      { wrapper: createWrapper() }
    )

    act(() => result.current.reviewVersionForPublish(2))
    act(() => result.current.cancelBreakingChangeWarning())
    await act(async () => {
      resolveReview?.(reviewResponse())
      await Promise.resolve()
    })

    expect(result.current.reviewedPublishVersion).toBeNull()
    expect(mocks.mutate).not.toHaveBeenCalled()
  })
})
