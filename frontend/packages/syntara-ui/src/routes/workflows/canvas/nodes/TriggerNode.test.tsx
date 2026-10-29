import { TriggerTypeEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

vi.mock('../../../../assets/eda.svg?react', () => ({
  default: () => <span data-testid="mock-eda-icon" />,
}))

import { ExecutionViewContext } from '../../../builder/ExecutionViewContext'

import { TriggerNodeComponent } from './TriggerNode'

const mockNodesConnectable = vi.hoisted(() => ({ value: true }))

vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number]; nodesConnectable: boolean }) => unknown) =>
    selector({ transform: [0, 0, 1], nodesConnectable: mockNodesConnectable.value }),
  useUpdateNodeInternals: () => vi.fn(),
  Handle: () => null,
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

vi.mock('./hooks/useNodeMenuActions', () => ({
  MenuNodeType: { TRIGGER: 'trigger' },
  useNodeMenuActions: () => [
    {
      id: 'edit',
      label: 'Edit',
      onClick: vi.fn(),
    },
  ],
}))

describe('TriggerNodeComponent', () => {
  const createNodeProps = (
    dataOverrides?: Partial<{ name: string; details: string | null; triggerType?: string }>
  ) => ({
    id: 'trigger-0',
    data: {
      name: 'Trigger',
      details: 'Manual',
      triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
      ...dataOverrides,
    },
    type: 'trigger' as const,
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

  it('identifies the Kafka trigger separately from its configured topic', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: 'Orders',
          triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE,
          details: 'Topic: orders.created',
        })}
      />
    )
    expect(screen.getByRole('heading', { name: 'Orders' })).toBeInTheDocument()
    expect(screen.getByText('Kafka Subscribe trigger')).toBeInTheDocument()
    expect(screen.getByText('Topic: orders.created')).toBeInTheDocument()
  })

  it('shows the step actions menu outside execution view', () => {
    render(<TriggerNodeComponent {...createNodeProps()} />)

    expect(screen.getByLabelText('Step actions menu')).toBeInTheDocument()
  })

  it('hides the step actions menu in execution view', () => {
    render(
      <ExecutionViewContext.Provider value={true}>
        <TriggerNodeComponent {...createNodeProps()} />
      </ExecutionViewContext.Provider>
    )

    expect(screen.queryByLabelText('Step actions menu')).not.toBeInTheDocument()
  })

  it('renders "Manual trigger" when the manual trigger details are shown', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: 'Trigger',
          details: null,
          triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
        })}
      />
    )

    expect(screen.getByText('Manual trigger')).toBeInTheDocument()
  })

  it('renders "Scheduled trigger" for scheduled triggers with cadence details', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: 'MyTrigger',
          details: 'Every 2 hours',
          triggerType: TriggerTypeEnum.SCHEDULED,
        })}
      />
    )

    expect(screen.getByText('Scheduled trigger')).toBeInTheDocument()
    expect(screen.getByText('Every 2 hours')).toBeInTheDocument()
  })

  it('renders names containing parentheses correctly', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: 'Hello(World)',
          details: 'Manual',
          triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
        })}
      />
    )

    expect(screen.getByText('Hello(World)')).toBeInTheDocument()
  })

  it('renders long trigger name without overflow', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: '${name_via_ai.analysis.default_trigger_configuration}',
          details: 'Every 5 minutes on weekdays',
          triggerType: TriggerTypeEnum.SCHEDULED,
        })}
      />
    )

    expect(screen.getByText('${name_via_ai.analysis.default_trigger_configuration}')).toBeInTheDocument()
    expect(screen.getByText('Every 5 minutes on weekdays')).toBeInTheDocument()
  })

  it('renders "Webhook trigger" label when webhook trigger has no details', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: 'My Webhook',
          details: null,
          triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
        })}
      />
    )

    expect(screen.getByText('Webhook trigger')).toBeInTheDocument()
  })

  it('renders webhook path detail instead of label when details are present', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: 'My Webhook',
          details: 'Webhook: /jira-updates',
          triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
        })}
      />
    )

    expect(screen.getByText('Webhook: /jira-updates')).toBeInTheDocument()
    expect(screen.queryByText('Webhook trigger')).not.toBeInTheDocument()
  })

  it('hides node menu when nodesConnectable is false', () => {
    mockNodesConnectable.value = false
    render(<TriggerNodeComponent {...createNodeProps()} />)
    expect(screen.queryByRole('button', { name: /step actions menu/i })).not.toBeInTheDocument()
    mockNodesConnectable.value = true
  })

  it('renders "Event-Driven Ansible trigger" label when EDA trigger has no details', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: 'My EDA Trigger',
          details: null,
          triggerType: TriggerTypeEnum.EDA_TRIGGER,
        })}
      />
    )

    expect(screen.getByText('Event-Driven Ansible trigger')).toBeInTheDocument()
  })

  it('renders EDA path detail instead of label when details are present', () => {
    render(
      <TriggerNodeComponent
        {...createNodeProps({
          name: 'My EDA Trigger',
          details: 'EDA: /eda-events',
          triggerType: TriggerTypeEnum.EDA_TRIGGER,
        })}
      />
    )

    expect(screen.getByText('EDA: /eda-events')).toBeInTheDocument()
    expect(screen.queryByText('Event-Driven Ansible trigger')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<TriggerNodeComponent {...createNodeProps()} />)
    // Exclude nested-interactive: pre-existing issue in shared NodeMenuWrapper component
    const results = await axe(container, { rules: { 'nested-interactive': { enabled: false } } })
    expect(results).toHaveNoViolations()
  })
})
