import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { createDefaultCondition, OPERATOR_LABELS } from '../../utils/expressions/defaults'
import type { ExpressionCondition as ExpressionConditionType, ComparisonOperator } from '../../utils/expressions/types'

import { ExpressionCondition } from './ExpressionCondition'

function ControlledExpressionCondition({ initialCondition }: { initialCondition: ExpressionConditionType }) {
  const [condition, setCondition] = useState(initialCondition)
  return (
    <ExpressionCondition
      condition={condition}
      onChange={(updates) => setCondition((prev) => ({ ...prev, ...updates }))}
    />
  )
}

async function selectOperator(user: ReturnType<typeof userEvent.setup>, operatorValue: ComparisonOperator) {
  const toggle = screen.getByRole('button', { name: 'Comparison operator' })
  await user.click(toggle)
  const option = await screen.findByRole('option', { name: OPERATOR_LABELS[operatorValue] })
  await user.click(option)
}

describe('ExpressionCondition', () => {
  const defaultProps = {
    condition: createDefaultCondition(),
    onChange: vi.fn(),
  }

  it('has no accessibility violations', async () => {
    const { container } = render(<ExpressionCondition {...defaultProps} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders condition with all fields', () => {
    render(<ExpressionCondition {...defaultProps} />)

    expect(screen.getByPlaceholderText('e.g. ${trigger.age}')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter or drag and drop value')).toBeInTheDocument()

    const operatorToggle = screen.getByRole('button', { name: 'Comparison operator' })
    expect(operatorToggle).toHaveTextContent(OPERATOR_LABELS['=='])
  })

  it('renders NOT checkbox', () => {
    render(<ExpressionCondition {...defaultProps} />)

    const notCheckbox = screen.getByRole('checkbox', { name: 'Negate condition' })
    expect(notCheckbox).toBeInTheDocument()
    expect(notCheckbox).not.toBeChecked()
  })

  it('shows NOT checkbox as checked when condition is negated', () => {
    const condition = { ...createDefaultCondition(), negate: true }
    render(<ExpressionCondition {...defaultProps} condition={condition} />)

    const notCheckbox = screen.getByRole('checkbox', { name: 'Negate condition' })
    expect(notCheckbox).toBeChecked()
  })

  it('calls onChange when NOT checkbox is toggled', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

    const notCheckbox = screen.getByRole('checkbox', { name: 'Negate condition' })
    await user.click(notCheckbox)

    expect(onChange).toHaveBeenCalledWith({ negate: true })
  })

  it('displays variable with ${} wrapper when not focused', () => {
    const condition = { ...createDefaultCondition(), variable: 'trigger.age' }
    render(<ExpressionCondition {...defaultProps} condition={condition} />)

    expect(screen.getByDisplayValue('${trigger.age}')).toBeInTheDocument()
  })

  it('keeps ${} wrapper when focused and on blur', async () => {
    const user = userEvent.setup()
    const condition = { ...createDefaultCondition(), variable: 'trigger.age' }
    render(<ExpressionCondition {...defaultProps} condition={condition} />)

    const fieldInput = screen.getByDisplayValue('${trigger.age}')
    await user.click(fieldInput)
    expect(screen.getByDisplayValue('${trigger.age}')).toBeInTheDocument()

    await user.tab()
    expect(screen.getByDisplayValue('${trigger.age}')).toBeInTheDocument()
  })

  it('strips ${} wrapper on blur when user pastes wrapped variable', async () => {
    const user = userEvent.setup()
    const condition = { ...createDefaultCondition(), variable: '' }
    render(<ControlledExpressionCondition initialCondition={condition} />)

    const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
    await user.click(fieldInput)
    await user.paste('${output.name}')
    expect(screen.getByDisplayValue('${output.name}')).toBeInTheDocument()

    await user.tab()
    expect(screen.getByDisplayValue('${output.name}')).toBeInTheDocument()
  })

  it('produces correct value when typing character by character', async () => {
    const user = userEvent.setup()
    const condition = { ...createDefaultCondition(), variable: '' }
    render(<ControlledExpressionCondition initialCondition={condition} />)

    const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
    await user.type(fieldInput, 'trigger.age')

    expect(screen.getByDisplayValue('trigger.age')).toBeInTheDocument()
    await user.tab()
    expect(screen.getByDisplayValue('${trigger.age}')).toBeInTheDocument()
  })

  it('does not strip ${ during typing', async () => {
    const user = userEvent.setup()
    const condition = { ...createDefaultCondition(), variable: '' }
    render(<ControlledExpressionCondition initialCondition={condition} />)

    const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
    await user.type(fieldInput, '$')
    expect(screen.getByDisplayValue('$')).toBeInTheDocument()
  })

  it('accepts drag-and-drop onto an empty field', () => {
    const onChange = vi.fn()
    render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

    const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
    const data: Record<string, string> = { 'text/plain': '${trigger.name}' }
    fireEvent.drop(fieldInput, {
      dataTransfer: { getData: (key: string) => data[key] ?? '' },
    })

    expect(onChange).toHaveBeenCalledWith({ variable: 'trigger.name' })
  })

  it('accepts drag-and-drop onto a field that previously had a value', async () => {
    const user = userEvent.setup()
    const condition = { ...createDefaultCondition(), variable: 'trigger.age' }
    render(<ControlledExpressionCondition initialCondition={condition} />)

    const fieldInput = screen.getByDisplayValue('${trigger.age}')
    await user.click(fieldInput)
    await user.clear(fieldInput)
    await user.tab()

    const emptyField = screen.getByPlaceholderText('e.g. ${trigger.age}')
    const data: Record<string, string> = { 'text/plain': '${output.result}' }
    fireEvent.drop(emptyField, {
      dataTransfer: { getData: (key: string) => data[key] ?? '' },
    })

    expect(screen.getByDisplayValue('${output.result}')).toBeInTheDocument()
  })

  it('commits variable on blur', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

    const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
    await user.type(fieldInput, 'trigger.age')
    await user.tab()

    expect(onChange).toHaveBeenCalledWith({ variable: 'trigger.age' })
  })

  it('updates operator field', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const condition = { ...createDefaultCondition(), operator: '==' as const }
    render(<ExpressionCondition {...defaultProps} condition={condition} onChange={onChange} />)

    await selectOperator(user, '>')

    expect(onChange).toHaveBeenCalledWith({ operator: '>' })
  })

  it('updates value field', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

    const valueInput = screen.getByPlaceholderText('Enter or drag and drop value')
    await user.type(valueInput, '18')

    expect(onChange).toHaveBeenCalled()
  })

  it('shows remove button when onRemove is provided', () => {
    render(<ExpressionCondition {...defaultProps} onRemove={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Remove condition' })).toBeInTheDocument()
  })

  it('does not show remove button when onRemove is not provided', () => {
    render(<ExpressionCondition {...defaultProps} />)

    expect(screen.queryByRole('button', { name: 'Remove condition' })).not.toBeInTheDocument()
  })

  it('calls onRemove when remove button is clicked', async () => {
    const user = userEvent.setup()
    const onRemove = vi.fn()
    render(<ExpressionCondition {...defaultProps} onRemove={onRemove} />)

    await user.click(screen.getByRole('button', { name: 'Remove condition' }))
    expect(onRemove).toHaveBeenCalledTimes(1)
  })

  it('renders all 14 operators with semantic grouping in dropdown', async () => {
    const user = userEvent.setup()
    const condition = createDefaultCondition()
    render(<ExpressionCondition {...defaultProps} condition={condition} />)

    const toggle = screen.getByRole('button', { name: 'Comparison operator' })
    await user.click(toggle)

    const options = await screen.findAllByRole('option')
    expect(options).toHaveLength(14)

    expect(screen.getByText('Comparison')).toBeInTheDocument()
    expect(screen.getByText('String')).toBeInTheDocument()
    expect(screen.getByText('Existence')).toBeInTheDocument()
    expect(screen.getByText('Length')).toBeInTheDocument()

    const operatorNames = options.map((opt) => opt.textContent)
    expect(operatorNames).toContain('is equal to')
    expect(operatorNames).toContain('is greater than')
    expect(operatorNames).toContain('contains')
    expect(operatorNames).toContain('exists')
    expect(operatorNames).toContain('length is equal to')
  })

  it('does not include removed negated operators (use NOT checkbox instead)', async () => {
    const user = userEvent.setup()
    const condition = createDefaultCondition()
    render(<ExpressionCondition {...defaultProps} condition={condition} />)

    const toggle = screen.getByRole('button', { name: 'Comparison operator' })
    await user.click(toggle)

    expect(screen.queryByRole('option', { name: 'is not equal to' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'does not contain' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'does not start with' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'does not end with' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'does not match regex' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'does not exist' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'length is not equal to' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'is not empty' })).not.toBeInTheDocument()
  })

  it('does not include removed Date/Time operators', async () => {
    const user = userEvent.setup()
    const condition = createDefaultCondition()
    render(<ExpressionCondition {...defaultProps} condition={condition} />)

    const toggle = screen.getByRole('button', { name: 'Comparison operator' })
    await user.click(toggle)

    expect(screen.queryByRole('option', { name: /is before$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /is after$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /is today/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /is in the past/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /is in the future/i })).not.toBeInTheDocument()
  })

  it('does not include removed Boolean operators', async () => {
    const user = userEvent.setup()
    const condition = createDefaultCondition()
    render(<ExpressionCondition {...defaultProps} condition={condition} />)

    const toggle = screen.getByRole('button', { name: 'Comparison operator' })
    await user.click(toggle)

    expect(screen.queryByRole('option', { name: 'is true' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'is false' })).not.toBeInTheDocument()
  })

  it('shows error state on variable when error prop is true and variable is empty', () => {
    const condition = { ...createDefaultCondition(), variable: '' }
    render(<ExpressionCondition {...defaultProps} condition={condition} error={true} />)

    const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
    expect(fieldInput).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows error state on value when error prop is true and value is empty', () => {
    const condition = { ...createDefaultCondition(), value: '', operator: '==' as const }
    render(<ExpressionCondition {...defaultProps} condition={condition} error={true} />)

    const valueInput = screen.getByPlaceholderText('Enter or drag and drop value')
    expect(valueInput).toHaveAttribute('aria-invalid', 'true')
  })

  it('clears error styling while typing into empty error field', async () => {
    const user = userEvent.setup()
    const condition = { ...createDefaultCondition(), variable: '' }
    render(<ExpressionCondition {...defaultProps} condition={condition} error={true} />)

    const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
    expect(fieldInput).toHaveAttribute('aria-invalid', 'true')

    await user.click(fieldInput)
    await user.type(fieldInput, 'trigger.age')
    expect(fieldInput).not.toHaveAttribute('aria-invalid', 'true')
  })

  it('does not show error state when error prop is false', () => {
    const condition = { ...createDefaultCondition(), variable: '', value: '' }
    render(<ExpressionCondition {...defaultProps} condition={condition} error={false} />)

    expect(screen.getByPlaceholderText('e.g. ${trigger.age}')).not.toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByPlaceholderText('Enter or drag and drop value')).not.toHaveAttribute('aria-invalid', 'true')
  })

  it('opens field help popover on click', async () => {
    const user = userEvent.setup()
    render(<ExpressionCondition {...defaultProps} />)

    const helpButton = screen.getByRole('button', { name: 'Field help' })
    await user.click(helpButton)

    expect(await screen.findByText(/The data point you want to evaluate/)).toBeInTheDocument()
  })

  it('opens operator help popover on click', async () => {
    const user = userEvent.setup()
    render(<ExpressionCondition {...defaultProps} />)

    const helpButton = screen.getByRole('button', { name: 'Operator help' })
    await user.click(helpButton)

    expect(await screen.findByText(/The logical test to apply/)).toBeInTheDocument()
  })

  it('opens value help popover on click', async () => {
    const user = userEvent.setup()
    const condition = { ...createDefaultCondition(), operator: '==' as const }
    render(<ExpressionCondition {...defaultProps} condition={condition} />)

    const helpButton = screen.getByRole('button', { name: 'Value help' })
    await user.click(helpButton)

    expect(await screen.findByText(/The specific criteria you are testing against/)).toBeInTheDocument()
  })

  it('opens NOT help popover on click', async () => {
    const user = userEvent.setup()
    render(<ExpressionCondition {...defaultProps} />)

    const helpButton = screen.getByRole('button', { name: 'NOT operator help' })
    await user.click(helpButton)

    expect(await screen.findByText(/Inverse the logic of this specific condition/)).toBeInTheDocument()
  })

  describe('Variable Validation', () => {
    it.each([
      { text: '${foo; DROP TABLE}', reason: 'invalid characters' },
      { text: '${foo.__proto__}', reason: 'reserved property name (__proto__)' },
      { text: '${}', reason: 'empty text after stripping' },
    ])('rejects drag-and-drop with $reason', ({ text }) => {
      const onChange = vi.fn()
      render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

      const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
      const data: Record<string, string> = { 'text/plain': text }
      fireEvent.drop(fieldInput, {
        dataTransfer: { getData: (key: string) => data[key] ?? '' },
      })

      expect(onChange).not.toHaveBeenCalled()
    })

    it('rejects typed variable with invalid characters on blur', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

      const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
      await user.type(fieldInput, 'foo bar!')
      await user.tab()

      expect(onChange).not.toHaveBeenCalledWith({ variable: 'foo bar!' })
    })

    it('accepts valid dotted variable paths via drag-and-drop', () => {
      const onChange = vi.fn()
      render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

      const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
      const data: Record<string, string> = { 'text/plain': '${fetch_order.output.riskScore}' }
      fireEvent.drop(fieldInput, {
        dataTransfer: { getData: (key: string) => data[key] ?? '' },
      })

      expect(onChange).toHaveBeenCalledWith({ variable: 'fetch_order.output.riskScore' })
    })

    it('shows inline error message when invalid variable is typed and blurred', async () => {
      const user = userEvent.setup()
      render(<ExpressionCondition {...defaultProps} onChange={vi.fn()} />)

      const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
      await user.type(fieldInput, '123bad')
      await user.tab()

      expect(screen.getByText(/Invalid variable name/)).toBeInTheDocument()
      expect(fieldInput).toHaveAttribute('aria-invalid', 'true')
    })

    it('clears inline error when user starts typing again', async () => {
      const user = userEvent.setup()
      render(<ExpressionCondition {...defaultProps} onChange={vi.fn()} />)

      const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
      await user.type(fieldInput, '123bad')
      await user.tab()
      expect(screen.getByText(/Invalid variable name/)).toBeInTheDocument()

      await user.click(fieldInput)
      await user.type(fieldInput, 'a')
      expect(screen.queryByText(/Invalid variable name/)).not.toBeInTheDocument()
    })

    it('rejects reserved property names (__proto__)', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

      const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
      await user.type(fieldInput, 'foo.__proto__.bar')
      await user.tab()

      expect(onChange).not.toHaveBeenCalledWith(expect.objectContaining({ variable: 'foo.__proto__.bar' }))
      expect(screen.getByText(/Invalid variable name/)).toBeInTheDocument()
    })

    it('rejects reserved property names (constructor)', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      render(<ExpressionCondition {...defaultProps} onChange={onChange} />)

      const fieldInput = screen.getByPlaceholderText('e.g. ${trigger.age}')
      await user.type(fieldInput, 'obj.constructor')
      await user.tab()

      expect(onChange).not.toHaveBeenCalledWith(expect.objectContaining({ variable: 'obj.constructor' }))
      expect(screen.getByText(/Invalid variable name/)).toBeInTheDocument()
    })
  })

  describe('Operator Selection', () => {
    it('changes operator when user selects new option', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      const condition = createDefaultCondition()

      render(<ExpressionCondition {...defaultProps} condition={condition} onChange={onChange} />)

      await selectOperator(user, 'contains')

      expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ operator: 'contains' }))
    })
  })

  describe('Value Field Visibility', () => {
    it('shows value field for binary operators (number category)', () => {
      const condition = { ...createDefaultCondition(), operator: '==' as const }
      render(<ExpressionCondition {...defaultProps} condition={condition} />)

      expect(screen.getByPlaceholderText('Enter or drag and drop value')).toBeInTheDocument()
    })

    it('hides value field for object operators - exists', () => {
      const condition = { ...createDefaultCondition(), operator: 'exists' as const }
      render(<ExpressionCondition {...defaultProps} condition={condition} />)

      expect(screen.queryByPlaceholderText('Enter or drag and drop value')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Value help' })).not.toBeInTheDocument()
    })

    it('hides value field for unary operators - exists with NOT checkbox', () => {
      const condition = { ...createDefaultCondition(), operator: 'exists' as const, negate: true }
      render(<ExpressionCondition {...defaultProps} condition={condition} />)

      expect(screen.queryByPlaceholderText('Enter or drag and drop value')).not.toBeInTheDocument()
    })

    it('hides value field for object operators - isEmpty', () => {
      const condition = { ...createDefaultCondition(), operator: 'isEmpty' as const }
      render(<ExpressionCondition {...defaultProps} condition={condition} />)

      expect(screen.queryByPlaceholderText('Enter or drag and drop value')).not.toBeInTheDocument()
    })

    it('hides value field for unary operators - isEmpty with NOT checkbox', () => {
      const condition = { ...createDefaultCondition(), operator: 'isEmpty' as const, negate: true }
      render(<ExpressionCondition {...defaultProps} condition={condition} />)

      expect(screen.queryByPlaceholderText('Enter or drag and drop value')).not.toBeInTheDocument()
    })

    it('shows value field for string operators', () => {
      const condition = { ...createDefaultCondition(), operator: 'contains' as const }
      render(<ExpressionCondition {...defaultProps} condition={condition} />)

      expect(screen.getByPlaceholderText('Enter or drag and drop value')).toBeInTheDocument()
    })

    it('shows value field for binary array operators (length)', () => {
      const condition = { ...createDefaultCondition(), operator: 'lengthEqualTo' as const }
      render(<ExpressionCondition {...defaultProps} condition={condition} />)

      expect(screen.getByPlaceholderText('Enter or drag and drop value')).toBeInTheDocument()
    })

    it('hides value field for unary/existence operators', () => {
      const condition = { ...createDefaultCondition(), operator: 'isEmpty' as const }
      render(<ExpressionCondition {...defaultProps} condition={condition} />)

      expect(screen.queryByPlaceholderText('Enter or drag and drop value')).not.toBeInTheDocument()
    })

    it('hides value field when switching to unary operator', async () => {
      const user = userEvent.setup()
      const condition = { ...createDefaultCondition(), operator: '==' as const }
      render(<ControlledExpressionCondition initialCondition={condition} />)

      expect(screen.getByPlaceholderText('Enter or drag and drop value')).toBeInTheDocument()

      await selectOperator(user, 'exists')

      expect(screen.queryByPlaceholderText('Enter or drag and drop value')).not.toBeInTheDocument()
    })

    it('shows value field when switching from unary to binary operator', async () => {
      const user = userEvent.setup()
      const condition = { ...createDefaultCondition(), operator: 'exists' as const }
      render(<ControlledExpressionCondition initialCondition={condition} />)

      expect(screen.queryByPlaceholderText('Enter or drag and drop value')).not.toBeInTheDocument()

      await selectOperator(user, '==')

      expect(screen.getByPlaceholderText('Enter or drag and drop value')).toBeInTheDocument()
    })
  })
})
