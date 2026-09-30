import { ExecutorTypeEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { NodeProps } from '@xyflow/react'
import { Position, ReactFlowProvider } from '@xyflow/react'
import type { ReactElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FlowNodeType } from '../../constants'

const viewportState = vi.hoisted(() => ({ zoom: 1 }))

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    useStore: (selector: (s: { transform: [number, number, number] }) => unknown) =>
      selector({ transform: [0, 0, viewportState.zoom] }),
    useUpdateNodeInternals: () => vi.fn(),
  }
})

import { SynStep } from './SynStep'

function renderWithFlow(ui: ReactElement) {
  return render(<ReactFlowProvider>{ui}</ReactFlowProvider>)
}

describe('SynStep semantic zoom', () => {
  afterEach(() => {
    viewportState.zoom = 1
    vi.clearAllMocks()
  })

  const baseNodeProps = {
    id: 'n1',
    data: { id: 'a1', type: 'condition', name: 'C' },
    selected: false,
    type: 'condition',
    dragging: false,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    isConnectable: true,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  } as unknown as NodeProps

  it('renders detailed children when zoom is above threshold', () => {
    viewportState.zoom = 0.75
    renderWithFlow(
      <SynStep
        nodeProps={baseNodeProps}
        topBarColor="var(--pf-t--global--color--nonstatus--blue--200)"
        semanticZoomSummary={{ title: 'T', typeLabel: 'Task Agent' }}
      >
        <span>Detailed body</span>
      </SynStep>
    )

    expect(screen.getByText('Detailed body')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'T, Task Agent' })).not.toBeInTheDocument()
  })

  it('renders semantic color block when zoom is at threshold', () => {
    viewportState.zoom = 0.5
    renderWithFlow(
      <SynStep
        nodeProps={baseNodeProps}
        topBarColor="var(--pf-t--global--color--nonstatus--blue--200)"
        semanticZoomSummary={{ title: 'Analyze', typeLabel: 'Task Agent' }}
      >
        <span>Detailed body</span>
      </SynStep>
    )

    expect(screen.queryByText('Detailed body')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze, Task Agent' })).toBeInTheDocument()
  })

  it('semantic zoom layout has no accessibility violations', async () => {
    viewportState.zoom = 0.5
    const { container } = renderWithFlow(
      <SynStep
        nodeProps={baseNodeProps}
        topBarColor="var(--pf-t--global--color--nonstatus--blue--200)"
        semanticZoomSummary={{ title: 'Analyze', typeLabel: 'Task Agent' }}
      >
        <span>Detailed body</span>
      </SynStep>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('SynStep validation and interaction', () => {
  afterEach(() => {
    viewportState.zoom = 1
    vi.clearAllMocks()
  })

  const baseNodeProps = {
    id: 'n1',
    data: { id: 'a1', type: 'condition', name: 'C' },
    selected: false,
    type: 'condition',
    dragging: false,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    isConnectable: true,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  } as unknown as NodeProps

  it('renders ValidationErrorBadge when __validationError is true', () => {
    const nodeProps = {
      ...baseNodeProps,
      data: { ...baseNodeProps.data, __validationError: true },
    } as unknown as NodeProps

    renderWithFlow(
      <SynStep nodeProps={nodeProps}>
        <span>Content</span>
      </SynStep>
    )

    expect(screen.getByTestId('validation-error-badge')).toBeInTheDocument()
    expect(screen.getByLabelText('Verification error')).toBeInTheDocument()
  })

  it('does not render ValidationErrorBadge when __validationError is false', () => {
    renderWithFlow(
      <SynStep nodeProps={baseNodeProps}>
        <span>Content</span>
      </SynStep>
    )

    expect(screen.queryByTestId('validation-error-badge')).not.toBeInTheDocument()
  })

  it('calls onClick when Enter key is pressed', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    renderWithFlow(
      <SynStep nodeProps={baseNodeProps} onClick={onClick}>
        <span>Content</span>
      </SynStep>
    )

    screen.getByRole('button').focus()
    await user.keyboard('{Enter}')

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('calls onClick when Space key is pressed', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    renderWithFlow(
      <SynStep nodeProps={baseNodeProps} onClick={onClick}>
        <span>Content</span>
      </SynStep>
    )

    screen.getByRole('button').focus()
    await user.keyboard(' ')

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('does not trigger onClick for arbitrary keys', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    renderWithFlow(
      <SynStep nodeProps={baseNodeProps} onClick={onClick}>
        <span>Content</span>
      </SynStep>
    )

    screen.getByRole('button').focus()
    await user.keyboard('a')

    expect(onClick).not.toHaveBeenCalled()
  })

  it('uses wide width for GENERIC node type', () => {
    const nodeProps = {
      ...baseNodeProps,
      type: FlowNodeType.GENERIC,
    } as unknown as NodeProps

    renderWithFlow(
      <SynStep nodeProps={nodeProps} rootTestId="node-panel">
        <span>Content</span>
      </SynStep>
    )

    expect(screen.getByTestId('node-panel')).toHaveStyle({ width: '360px' })
  })

  it('uses wide width for TASK node with agentic executor', () => {
    const nodeProps = {
      ...baseNodeProps,
      type: FlowNodeType.TASK,
      data: { id: 'a1', type: ExecutorTypeEnum.AGENTIC, name: 'Agent' },
    } as unknown as NodeProps

    renderWithFlow(
      <SynStep nodeProps={nodeProps} rootTestId="node-panel">
        <span>Content</span>
      </SynStep>
    )

    expect(screen.getByTestId('node-panel')).toHaveStyle({ width: '360px' })
  })

  it('responds to expandAll and collapseAll events', () => {
    renderWithFlow(
      <SynStep nodeProps={baseNodeProps} collapsible>
        <span>Content</span>
      </SynStep>
    )

    expect(screen.getByText('Content')).toBeInTheDocument()
  })

  it('renders with dashed border style when hasDashedBorder is true', () => {
    renderWithFlow(
      <SynStep nodeProps={baseNodeProps} hasDashedBorder rootTestId="node-panel" style={{ opacity: 1 }}>
        <span>Content</span>
      </SynStep>
    )

    expect(screen.getByTestId('node-panel')).toBeInTheDocument()
  })

  it('renders selected node with outline', () => {
    const selectedProps = {
      ...baseNodeProps,
      selected: true,
    } as unknown as NodeProps

    renderWithFlow(
      <SynStep nodeProps={selectedProps} topBarColor="blue" rootTestId="node-panel">
        <span>Content</span>
      </SynStep>
    )

    expect(screen.getByTestId('node-panel')).toBeInTheDocument()
  })

  it('renders disabled node with dashed gray border', () => {
    const disabledProps = {
      ...baseNodeProps,
      data: { ...baseNodeProps.data, settings: { disabled: true } },
    } as unknown as NodeProps

    renderWithFlow(
      <SynStep nodeProps={disabledProps} rootTestId="node-panel">
        <span>Content</span>
      </SynStep>
    )

    expect(screen.getByTestId('node-panel')).toHaveStyle({ opacity: '0.5' })
  })

  it('handles re-render with unchanged props', () => {
    const { rerender } = renderWithFlow(
      <SynStep nodeProps={baseNodeProps} rootTestId="node-panel">
        <span>Content</span>
      </SynStep>
    )
    rerender(
      <ReactFlowProvider>
        <SynStep nodeProps={baseNodeProps} rootTestId="node-panel">
          <span>Content</span>
        </SynStep>
      </ReactFlowProvider>
    )
    expect(screen.getByTestId('node-panel')).toBeInTheDocument()
  })
})
