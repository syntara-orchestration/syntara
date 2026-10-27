import { ExecutorTypeEnum } from '@syntara/contracts'
import { act, render, screen } from '@testing-library/react'
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
    useStore: (selector: (s: { transform: [number, number, number]; nodesConnectable: boolean }) => unknown) =>
      selector({ transform: [0, 0, viewportState.zoom], nodesConnectable: true }),
    useUpdateNodeInternals: () => vi.fn(),
  }
})

import { SynStep } from './SynStep'
import { SynStepBody } from './SynStepBody'
import { SynStepExpandedAllContext } from './SynStepExpandedAllContext'

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
    expect(screen.queryByText('T')).not.toBeInTheDocument()
  })

  it('renders icon-only semantic zoom tile when zoom is at threshold', () => {
    viewportState.zoom = 0.5
    renderWithFlow(
      <SynStep
        nodeProps={baseNodeProps}
        topBarColor="var(--pf-t--global--color--nonstatus--blue--200)"
        semanticZoomSummary={{ title: 'Analyze', typeLabel: 'Task Agent' }}
        semanticZoomIcon={<span data-testid="semantic-zoom-icon" />}
      >
        <span>Detailed body</span>
      </SynStep>
    )

    expect(screen.queryByText('Detailed body')).not.toBeInTheDocument()
    expect(screen.queryByText('Analyze')).not.toBeInTheDocument()
    expect(screen.queryByText('Task Agent')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze, Task Agent' })).toBeInTheDocument()
    expect(screen.getByTestId('semantic-zoom-icon')).toBeInTheDocument()
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

  it('uses tile width and semantic-zoom connection handles at low zoom', () => {
    viewportState.zoom = 0.5
    renderWithFlow(
      <SynStep
        rootTestId="syn-step-semantic-zoom"
        nodeProps={{ ...baseNodeProps, selected: true }}
        semanticZoomSummary={{ title: 'Branch', typeLabel: 'Condition' }}
        semanticZoomIcon={<span data-testid="semantic-zoom-icon" />}
        semanticZoomMenuActions={[{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]}
        semanticZoomBranchSources={[{ id: 'true', ariaLabel: 'True branch output' }]}
        style={{ borderTopLeftRadius: '8px' }}
        enableStart
        enableEnd
        disableSource
        reverseHandles
      >
        <span>Detailed body</span>
      </SynStep>
    )

    expect(screen.getByTestId('syn-step-semantic-zoom')).toHaveStyle({ width: '224px' })
    expect(screen.getByTestId('semantic-zoom-icon')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Branch, Condition' })).toBeInTheDocument()
    expect(screen.getByLabelText('True branch output')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit Branch' })).toBeInTheDocument()
  })

  it('shows execution and validation badges on semantic zoom tiles', () => {
    viewportState.zoom = 0.5
    const nodeProps = {
      ...baseNodeProps,
      data: { ...baseNodeProps.data, __validationError: true },
    } as unknown as NodeProps

    renderWithFlow(
      <SynStep
        nodeProps={nodeProps}
        semanticZoomSummary={{ title: 'Analyze', typeLabel: 'Task Agent' }}
        executionState={{ status: 'failed' }}
      >
        <span>Detailed body</span>
      </SynStep>
    )

    expect(screen.getByRole('img', { name: 'Error' })).toBeInTheDocument()
    expect(screen.getByTestId('validation-error-badge')).toBeInTheDocument()
  })

  it('renders dashed-border semantic zoom tile when placeholder styling is set', () => {
    viewportState.zoom = 0.5
    renderWithFlow(
      <SynStep
        nodeProps={{ ...baseNodeProps, selected: true }}
        hasDashedBorder
        semanticZoomSummary={{ title: 'Pick type', typeLabel: 'Generic' }}
      >
        <span>Detailed body</span>
      </SynStep>
    )

    expect(screen.getByRole('button', { name: 'Pick type, Generic' })).toBeInTheDocument()
  })

  it('omits trigger pill radius on semantic zoom tiles', () => {
    viewportState.zoom = 0.5
    renderWithFlow(
      <SynStep
        nodeProps={baseNodeProps}
        semanticZoomSummary={{ title: 'Trigger', typeLabel: 'Webhook' }}
        style={{ borderTopLeftRadius: '75px', borderBottomLeftRadius: '75px' }}
      >
        <span>Detailed body</span>
      </SynStep>
    )

    expect(screen.getByRole('button', { name: 'Trigger, Webhook' })).toBeInTheDocument()
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
    const expandAllEvent = new EventTarget()
    const collapseAllEvent = new EventTarget()

    renderWithFlow(
      <SynStepExpandedAllContext.Provider value={{ expandAllEvent, collapseAllEvent }}>
        <SynStep nodeProps={baseNodeProps} collapsible>
          <SynStepBody>
            <span>Content</span>
          </SynStepBody>
        </SynStep>
      </SynStepExpandedAllContext.Provider>
    )

    expect(screen.getByText('Content')).toBeInTheDocument()

    act(() => {
      collapseAllEvent.dispatchEvent(new Event('collapseAll'))
    })
    expect(screen.queryByText('Content')).not.toBeInTheDocument()

    act(() => {
      expandAllEvent.dispatchEvent(new Event('expandAll'))
    })
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
