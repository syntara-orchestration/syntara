import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import type { NodeKind } from '../../../../hooks/useNodeKindsQuery'

import { useOptimisticNodeKindEnabled } from './useOptimisticNodeKindEnabled'

function kind(overrides: Partial<NodeKind> & { kind: string }): NodeKind {
  return {
    category: 'action',
    enabled: true,
    switchable: true,
    deniable_actions: ['write', 'execute'],
    can_write: true,
    attributes: [],
    ...overrides,
  }
}

const nodeKinds = [kind({ kind: 'script' }), kind({ kind: 'agentic' })]

/** Run a transition Action and let its awaited mutation settle before asserting. */
async function runAction(toggle: () => void) {
  await act(async () => {
    toggle()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

describe('useOptimisticNodeKindEnabled', () => {
  let setEnabled: Mock<(args: { params: { path: { kind: string } }; body: { enabled: boolean } }) => Promise<unknown>>
  let onSuccess: Mock<(kind: string, enabled: boolean) => Promise<unknown>>
  let onError: Mock<(title: string, error: unknown) => void>

  beforeEach(() => {
    setEnabled = vi
      .fn<(args: { params: { path: { kind: string } }; body: { enabled: boolean } }) => Promise<unknown>>()
      .mockResolvedValue({})
    onSuccess = vi.fn<(kind: string, enabled: boolean) => Promise<unknown>>().mockResolvedValue(undefined)
    onError = vi.fn<(title: string, error: unknown) => void>()
  })

  function renderTarget() {
    return renderHook(() => useOptimisticNodeKindEnabled({ nodeKinds, setEnabled, onSuccess, onError }))
  }

  it('returns the server list untouched before any toggle', () => {
    const { result } = renderTarget()

    expect(result.current.nodeKinds).toEqual(nodeKinds)
  })

  it('calls the kill-switch endpoint with the kind in the path', async () => {
    const { result } = renderTarget()

    await runAction(() => result.current.setNodeKindEnabled('script', false))

    expect(setEnabled).toHaveBeenCalledWith({ params: { path: { kind: 'script' } }, body: { enabled: false } })
  })

  it('awaits the success callback so server state converges inside the Action', async () => {
    const { result } = renderTarget()

    await runAction(() => result.current.setNodeKindEnabled('agentic', false))

    expect(onSuccess).toHaveBeenCalledWith('agentic', false)
    expect(onError).not.toHaveBeenCalled()
  })

  it('reports a failure with a disable-specific title', async () => {
    const failure = { detail: 'nope' }
    setEnabled.mockRejectedValue(failure)
    const { result } = renderTarget()

    await runAction(() => result.current.setNodeKindEnabled('script', false))

    expect(onError).toHaveBeenCalledWith('Failed to disable script nodes', failure)
  })

  it('reports a failure with an enable-specific title', async () => {
    setEnabled.mockRejectedValue(new Error('nope'))
    const { result } = renderTarget()

    await runAction(() => result.current.setNodeKindEnabled('script', true))

    expect(onError).toHaveBeenCalledWith('Failed to enable script nodes', expect.any(Error))
  })

  it('rolls back to the server list when the Action fails', async () => {
    setEnabled.mockRejectedValue(new Error('nope'))
    const { result } = renderTarget()

    await runAction(() => result.current.setNodeKindEnabled('script', false))

    expect(result.current.nodeKinds).toEqual(nodeKinds)
  })
})
