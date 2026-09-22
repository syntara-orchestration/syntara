import type { PermissionCheckActivity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { PermissionCheckNodeComponent, PermissionCheckNodeDetails } from './PermissionCheckNode'

const handleCalls: { type: string; id?: string; position: string }[] = []

vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number] }) => unknown) => selector({ transform: [0, 0, 1] }),
  useUpdateNodeInternals: () => vi.fn(),
  useEdges: () => [],
  Handle: (props: { type: string; id?: string; position: string }) => {
    handleCalls.push({ type: props.type, id: props.id, position: props.position })
    return null
  },
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

const baseNode = {
  type: 'permission_check',
  id: 'permission_check_1',
  name: 'Was restart allowed',
  parameters: {},
} as PermissionCheckActivity

function createNodeProps(data: PermissionCheckActivity) {
  return {
    id: data.id,
    data,
    type: 'permission_check' as const,
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
  }
}

describe('PermissionCheckNodeComponent', () => {
  it('renders the node name', () => {
    render(<PermissionCheckNodeComponent {...createNodeProps(baseNode)} />)

    expect(screen.getByText('Was restart allowed')).toBeInTheDocument()
  })

  it('renders the "Permission check" type label', () => {
    render(<PermissionCheckNodeComponent {...createNodeProps(baseNode)} />)

    expect(screen.getByText('Permission check')).toBeInTheDocument()
  })

  it('renders the Allowed and Denied output ports in order', () => {
    render(<PermissionCheckNodeComponent {...createNodeProps(baseNode)} />)

    expect(screen.getByTestId('branch-handle-allowed')).toBeInTheDocument()
    expect(screen.getByTestId('branch-handle-denied')).toBeInTheDocument()

    const ports = screen.getAllByText(/^(Allowed|Denied)$/)
    expect(ports[0]).toHaveTextContent('Allowed')
    expect(ports[1]).toHaveTextContent('Denied')
  })

  it('exposes exactly one target handle and two named source handles', () => {
    handleCalls.length = 0
    render(<PermissionCheckNodeComponent {...createNodeProps(baseNode)} />)

    const targets = handleCalls.filter((call) => call.type === 'target')
    const sources = handleCalls.filter((call) => call.type === 'source')

    expect(targets).toHaveLength(1)
    expect(sources.map((call) => call.id)).toEqual(['allowed', 'denied'])
  })

  it('does not render an expand/collapse toggle', () => {
    render(<PermissionCheckNodeComponent {...createNodeProps(baseNode)} />)

    expect(screen.queryByTestId('node-expand-toggle')).not.toBeInTheDocument()
  })

  it('falls back to a placeholder title when the node has no name', () => {
    const unnamed = { type: 'permission_check', id: 'permission_check_2', parameters: {} } as PermissionCheckActivity

    render(<PermissionCheckNodeComponent {...createNodeProps(unnamed)} />)

    expect(screen.getByText('Untitled permission check')).toBeInTheDocument()
  })

  it('renders with a denied execution state without crashing', () => {
    const withExecution = {
      ...baseNode,
      __executionState: { status: 'denied', started_at: '2024-01-01T00:00:00Z' },
    } as PermissionCheckActivity

    render(<PermissionCheckNodeComponent {...createNodeProps(withExecution)} />)

    expect(screen.getByText('Was restart allowed')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<PermissionCheckNodeComponent {...createNodeProps(baseNode)} />)

    const results = await axe(container)

    expect(results).toHaveNoViolations()
  })
})

describe('PermissionCheckNodeDetails', () => {
  it('renders the activity name as the title', () => {
    render(<PermissionCheckNodeDetails permissionCheckActivity={baseNode} />)

    expect(screen.getByText('Was restart allowed')).toBeInTheDocument()
  })

  it('renders declared outputs', () => {
    const withOutputs = { ...baseNode, outputs: { allowed: '${permission_check_1.allowed}' } }

    render(<PermissionCheckNodeDetails permissionCheckActivity={withOutputs} />)

    expect(screen.getByText('Outputs')).toBeInTheDocument()
  })
})
