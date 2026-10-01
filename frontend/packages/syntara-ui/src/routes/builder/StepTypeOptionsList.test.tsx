import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { StepTypeOption } from './StepTypeOptionsList'
import { StepTypeOptionsList } from './StepTypeOptionsList'

vi.mock('../workflows/canvas/nodes/renderStepIcon', () => ({
  renderStepIcon: vi.fn((_icon, id) => <span data-testid={`icon-${id}`}>Icon</span>),
}))

vi.mock('./utils/stepIcons', () => ({
  resolveIconForType: vi.fn(({ stepTypeId }: { stepTypeId: string }) => ({
    icon: vi.fn(),
    id: stepTypeId,
  })),
}))

const mockStepTypes: StepTypeOption[] = [
  { id: 'action', label: 'Action Step', icon: vi.fn(), description: 'Perform an action' },
  { id: 'condition', label: 'Condition Step', icon: vi.fn(), description: 'Add conditional logic' },
  { id: 'loop', label: 'Loop Step', icon: vi.fn() },
]

describe('StepTypeOptionsList', () => {
  it('renders all step type options with labels and icons', () => {
    const onSelect = vi.fn()
    render(<StepTypeOptionsList stepTypes={mockStepTypes} onSelect={onSelect} />)

    expect(screen.getByText('Action Step')).toBeInTheDocument()
    expect(screen.getByText('Condition Step')).toBeInTheDocument()
    expect(screen.getByText('Loop Step')).toBeInTheDocument()

    expect(screen.getByTestId('icon-action')).toBeInTheDocument()
    expect(screen.getByTestId('icon-condition')).toBeInTheDocument()
    expect(screen.getByTestId('icon-loop')).toBeInTheDocument()
  })

  it('renders descriptions when provided', () => {
    const onSelect = vi.fn()
    render(<StepTypeOptionsList stepTypes={mockStepTypes} onSelect={onSelect} />)

    expect(screen.getByText('Perform an action')).toBeInTheDocument()
    expect(screen.getByText('Add conditional logic')).toBeInTheDocument()
  })

  it('does not render description element when description is not provided', () => {
    const onSelect = vi.fn()
    const stepTypesWithoutDesc: StepTypeOption[] = [{ id: 'test', label: 'Test step', icon: vi.fn() }]
    render(<StepTypeOptionsList stepTypes={stepTypesWithoutDesc} onSelect={onSelect} />)

    expect(screen.getByText('Test step')).toBeInTheDocument()

    expect(screen.queryByTestId('step-type-description')).not.toBeInTheDocument()
  })

  it('calls onSelect with correct stepTypeId when clicked', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<StepTypeOptionsList stepTypes={mockStepTypes} onSelect={onSelect} />)

    await user.click(screen.getByRole('button', { name: 'Action Step' }))
    expect(onSelect).toHaveBeenCalledWith('action')

    await user.click(screen.getByRole('button', { name: 'Condition Step' }))
    expect(onSelect).toHaveBeenCalledWith('condition')
  })

  it('calls onSelect when Enter key is pressed', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<StepTypeOptionsList stepTypes={mockStepTypes} onSelect={onSelect} />)

    const actionButton = screen.getByRole('button', { name: 'Action Step' })
    actionButton.focus()
    await user.keyboard('{Enter}')

    expect(onSelect).toHaveBeenCalledWith('action')
  })

  it('calls onSelect when Space key is pressed', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<StepTypeOptionsList stepTypes={mockStepTypes} onSelect={onSelect} />)

    const conditionButton = screen.getByRole('button', { name: 'Condition Step' })
    conditionButton.focus()
    await user.keyboard(' ')

    expect(onSelect).toHaveBeenCalledWith('condition')
  })

  it('renders with correct accessibility attributes', () => {
    const onSelect = vi.fn()
    render(<StepTypeOptionsList stepTypes={mockStepTypes} onSelect={onSelect} />)

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(3)

    buttons.forEach((button) => {
      expect(button).toHaveAttribute('tabIndex', '0')
    })
  })

  it('renders empty when stepTypes array is empty', () => {
    const onSelect = vi.fn()
    const { container } = render(<StepTypeOptionsList stepTypes={[]} onSelect={onSelect} />)

    expect(container).toBeEmptyDOMElement()
  })
})
