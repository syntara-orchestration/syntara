import type { Activity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { FormPromptNodeComponent } from './FormPromptNode'

vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number] }) => unknown) => selector({ transform: [0, 0, 1] }),
  useUpdateNodeInternals: () => vi.fn(),
  useEdges: () => [],
  Handle: () => null,
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

vi.mock('../../stores/useExecutionStore', () => ({
  useExecutionStore: (
    selector: (state: {
      activityStates: Map<string, { status: string; startedAt?: string; started_at?: string }>
    }) => unknown
  ) =>
    selector({
      activityStates: new Map([['form-1', { status: 'waiting', startedAt: '2026-10-01T10:00:00.000Z' }]]),
    }),
}))

describe('FormPromptNodeComponent', () => {
  const baseFormPromptNode = {
    type: 'form_prompt',
    id: 'form-1',
    name: 'Customer survey',
    parameters: {
      form_definition: { fields: [{ id: 'f1' }, { id: 'f2' }] },
    },
  } as Activity

  const createNodeProps = (data: Activity) => ({
    id: data.id,
    data,
    type: 'form_prompt' as const,
    position: { x: 0, y: 0 },
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    selected: false,
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    selectable: true,
    deletable: true,
    draggable: true,
  })

  it('renders form prompt node with field count and branch labels', () => {
    render(<FormPromptNodeComponent {...createNodeProps(baseFormPromptNode)} />)

    expect(screen.getByText('Form')).toBeInTheDocument()
    expect(screen.getByText('Fields')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Submitted')).toBeInTheDocument()
    expect(screen.getByText('Fallback')).toBeInTheDocument()
  })

  it('shows zero fields when form_definition is missing', () => {
    const node: Activity = {
      ...baseFormPromptNode,
      parameters: {},
    }

    render(<FormPromptNodeComponent {...createNodeProps(node)} />)

    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('renders when execution badge metadata is enabled', () => {
    const node: Activity = {
      ...baseFormPromptNode,
      name: undefined,
      metadata: { __showExecutionBadge: true },
    }
    const data = {
      ...node,
      __executionState: { status: 'running' as const, started_at: '2026-01-01T00:00:00Z' },
    } as Activity

    render(<FormPromptNodeComponent {...createNodeProps(data)} />)

    expect(screen.getByText('Untitled Form')).toBeInTheDocument()
  })

  it('merges live execution store status into badge state', () => {
    const data = {
      ...baseFormPromptNode,
      metadata: { __showExecutionBadge: true },
      __executionState: { status: 'running' as const, started_at: '2026-01-01T00:00:00Z' },
    } as Activity

    render(<FormPromptNodeComponent {...createNodeProps(data)} />)

    expect(screen.getByText('Customer survey')).toBeInTheDocument()
  })
})
