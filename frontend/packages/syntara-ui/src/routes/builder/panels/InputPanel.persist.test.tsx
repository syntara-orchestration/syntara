import { render, screen } from '@testing-library/react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMockDataStore } from '../../../stores/useMockDataStore'

import { InputPanel } from './InputPanel'

const mockUseUpstreamNodes = vi.fn<(...args: unknown[]) => { id: string; name: string; type: string }[]>()
vi.mock('./hooks/useUpstreamNodes', () => ({
  useUpstreamNodes: (...args: unknown[]) =>
    mockUseUpstreamNodes(...args) as { id: string; name: string; type: string }[],
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: unknown) => unknown) =>
    selector({
      currentWorkflow: {
        workflow: { activities: [] },
        triggers: [],
      },
    }),
}))

const upstreamNodes = [{ id: 'script-a', name: 'Script A', type: 'script' }]

describe('InputPanel pinned mock persistence', () => {
  beforeEach(() => {
    act(() => {
      useMockDataStore.setState({ pinnedData: {}, refCounts: {} })
    })
    mockUseUpstreamNodes.mockReturnValue(upstreamNodes)
  })

  it('still shows the pinned badge after the panel is unmounted and remounted', () => {
    act(() => {
      useMockDataStore.getState().pinInputMock('script-b', 'script-a', { stdout: 'alpha' })
    })

    const { unmount } = render(<InputPanel nodeId="script-b" />)
    expect(screen.getByText('Mock data pinned (1)')).toBeInTheDocument()

    unmount()
    expect(screen.queryByText('Mock data pinned (1)')).not.toBeInTheDocument()

    render(<InputPanel nodeId="script-b" />)
    expect(screen.getByText('Mock data pinned (1)')).toBeInTheDocument()
  })
})
