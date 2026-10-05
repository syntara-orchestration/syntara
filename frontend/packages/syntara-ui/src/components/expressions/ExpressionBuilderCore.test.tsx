import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { createDefaultCondition, createDefaultGroup } from '../../utils/expressions/defaults'

import { ExpressionBuilderCore } from './ExpressionBuilderCore'
import { EXPRESSION_MODE_LABELS } from './expressionBuilderLabels'
import { prepareRootNode } from './prepareRootNode'

const MODE_LABELS = EXPRESSION_MODE_LABELS

const MODE_TOGGLE_NAME = new RegExp(`${MODE_LABELS.visual}|${MODE_LABELS.raw}`)

async function selectMode(user: ReturnType<typeof userEvent.setup>, mode: 'visual' | 'raw') {
  const toggle = screen.getByRole('button', { name: MODE_TOGGLE_NAME })
  await user.click(toggle)
  const option = await screen.findByRole('option', { name: MODE_LABELS[mode] })
  await user.click(option)
}

function expectModeValue(mode: 'visual' | 'raw') {
  const toggle = screen.getByRole('button', { name: MODE_LABELS[mode] })
  expect(toggle).toHaveTextContent(MODE_LABELS[mode])
}

describe('prepareRootNode', () => {
  it('wraps a condition node in a group', () => {
    const condition = createDefaultCondition()
    const expression = { root: condition }

    const result = prepareRootNode(expression)

    const { children: resultChildren } = result
    expect(result.type).toBe('group')
    expect(resultChildren).toHaveLength(1)
    expect(resultChildren[0]).toBe(condition)
    expect(result.operator).toBe('AND')
  })

  it('returns a group node as-is', () => {
    const group = createDefaultGroup('OR')
    const expression = { root: group }

    const result = prepareRootNode(expression)

    expect(result).toBe(group)
    expect(result.type).toBe('group')
    expect(result.operator).toBe('OR')
  })

  it('creates a default group when root is null', () => {
    const result = prepareRootNode({ root: null })

    const { children: resultChildren } = result
    expect(result.type).toBe('group')
    expect(result.operator).toBe('AND')
    expect(resultChildren).toHaveLength(1)
    expect(resultChildren[0].type).toBe('condition')
  })
})

describe('ExpressionBuilderCore', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<ExpressionBuilderCore value="" onChange={vi.fn()} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders with empty value in visual mode', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    expect(screen.getByRole('button', { name: MODE_LABELS.visual })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add condition' })).toBeInTheDocument()
  })

  it('renders mode selector with visual and raw options', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    expectModeValue('visual')

    const toggle = screen.getByRole('button', { name: MODE_TOGGLE_NAME })
    await user.click(toggle)

    expect(screen.getByRole('option', { name: EXPRESSION_MODE_LABELS.visual })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: EXPRESSION_MODE_LABELS.raw })).toBeInTheDocument()
  })

  it('parses valid expression and renders in visual mode', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="${input.age >= 18}" onChange={onChange} />)

    expectModeValue('visual')
    expect(screen.getByRole('button', { name: 'Add condition' })).toBeInTheDocument()
  })

  it('starts in raw mode for unparseable expression', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="${invalid syntax" onChange={onChange} />)

    expectModeValue('raw')
  })

  it('switches from visual to raw mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    await selectMode(user, 'raw')

    await waitFor(() => {
      expect(screen.getByLabelText('Raw expression')).toBeInTheDocument()
    })
  })

  it('switches from raw to visual mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="${input.age >= 18}" onChange={onChange} />)

    await selectMode(user, 'raw')
    await waitFor(() => {
      expect(screen.getByLabelText('Raw expression')).toBeInTheDocument()
    })

    await selectMode(user, 'visual')
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Add condition' })).toBeInTheDocument()
    })
  })

  it('updates field in visual mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    const fieldInputs = screen.getAllByPlaceholderText('Enter or drag and drop value')
    await user.type(fieldInputs[0], 'test')

    expect(fieldInputs[0]).toHaveValue('test')
  })

  it('updates raw text when typing', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="${test}" onChange={onChange} />)

    await selectMode(user, 'raw')

    const rawInput = await screen.findByLabelText('Raw expression')
    await user.clear(rawInput)
    await user.type(rawInput, 'updated')

    expect(rawInput).toHaveValue('updated')
  })

  it('serializes visual expression when switching to raw mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="${input.age} >= 18" onChange={onChange} />)

    await selectMode(user, 'raw')

    const rawInput = await screen.findByLabelText('Raw expression')
    expect(rawInput).toHaveValue('${input.age} >= 18')
  })

  it('handles external value change', async () => {
    const onChange = vi.fn()
    const { rerender } = render(<ExpressionBuilderCore value="" onChange={onChange} />)

    rerender(<ExpressionBuilderCore value="${input.score > 50}" onChange={onChange} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Add condition' })).toBeInTheDocument()
    })
  })

  it('does not emit change when value prop changes to same value', () => {
    const onChange = vi.fn()
    const { rerender } = render(<ExpressionBuilderCore value="${input.age >= 18}" onChange={onChange} />)

    onChange.mockClear()

    rerender(<ExpressionBuilderCore value="${input.age >= 18}" onChange={onChange} />)

    expect(onChange).not.toHaveBeenCalled()
  })

  it('renders with placeholder in raw mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} placeholder="Custom placeholder" />)

    await selectMode(user, 'raw')

    expect(await screen.findByPlaceholderText('Custom placeholder')).toBeInTheDocument()
  })

  it('renders with error prop', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} error={true} />)

    expect(screen.getByRole('button', { name: 'Add condition' })).toBeInTheDocument()
  })

  it('renders with custom id', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} id="custom-builder-id" />)

    expect(screen.getByRole('group', { name: 'Condition' })).toHaveAttribute('id', 'custom-builder-id')
  })

  it('renders with aria-labelledby', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} aria-labelledby="custom-label" />)

    const groups = screen.getAllByRole('group')
    const builderGroup = groups.find((g) => g.hasAttribute('aria-labelledby'))
    expect(builderGroup).toBeDefined()
    expect(builderGroup).toHaveAttribute('aria-labelledby', 'custom-label')
    expect(builderGroup).not.toHaveAttribute('aria-label')
  })

  it('renders with default aria-label when no aria-labelledby', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    expect(screen.getByRole('group', { name: 'Condition' })).toBeInTheDocument()
  })

  it('adds condition in visual mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Add condition' }))

    const fieldInputs = screen.getAllByPlaceholderText('Enter or drag and drop value')
    expect(fieldInputs.length).toBeGreaterThan(1)
  })

  it('adds group in visual mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Add group' }))

    const groupLabels = screen.getAllByText('Group')
    expect(groupLabels.length).toBeGreaterThan(0)
  })

  it('removes condition when only one left creates default condition', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="${input.age >= 18}" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Add condition' }))

    const removeButtons = screen.getAllByRole('button', { name: 'Remove condition' })
    await user.click(removeButtons[0])

    const fieldInputs = screen.getAllByPlaceholderText('Enter or drag and drop value')
    expect(fieldInputs.length).toBeGreaterThan(0)
  })

  it('wraps single condition in group for consistent UI', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="${input.age >= 18}" onChange={onChange} />)

    expect(screen.getByRole('button', { name: 'Add condition' })).toBeInTheDocument()
  })

  it('handles empty expression in visual mode', () => {
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    expect(screen.getByRole('button', { name: 'Add condition' })).toBeInTheDocument()
  })

  it('changes operator in visual mode', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Add condition' }))

    const operatorToggle = screen.getByRole('button', { name: 'Logical operator' })
    expect(operatorToggle).toHaveTextContent('AND')

    await user.click(operatorToggle)
    const orOption = await screen.findByRole('option', { name: 'OR' })
    await user.click(orOption)

    expect(screen.getByRole('button', { name: 'Logical operator' })).toHaveTextContent('OR')
  })

  it('allows switching to visual mode with invalid raw expression', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionBuilderCore value="" onChange={onChange} />)

    await selectMode(user, 'raw')

    const rawInput = await screen.findByLabelText('Raw expression')
    await user.type(rawInput, 'invalid')

    await selectMode(user, 'visual')

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Add condition' })).toBeInTheDocument()
    })
  })

  describe('External value change mode sync', () => {
    it('preserves raw mode when external value changes to a parseable expression', () => {
      const onChange = vi.fn()
      const { rerender } = render(<ExpressionBuilderCore value="unparseable syntax {{" onChange={onChange} />)

      expectModeValue('raw')

      rerender(<ExpressionBuilderCore value='${status} == "active"' onChange={onChange} />)

      expectModeValue('raw')
    })

    it('preserves visual mode when external value changes to an unparseable expression', () => {
      const onChange = vi.fn()
      const { rerender } = render(<ExpressionBuilderCore value='${status} == "active"' onChange={onChange} />)

      expectModeValue('visual')

      rerender(<ExpressionBuilderCore value="unparseable {{syntax" onChange={onChange} />)

      expectModeValue('visual')
    })

    it('preserves visual mode when external value changes to another parseable expression', () => {
      const onChange = vi.fn()
      const { rerender } = render(<ExpressionBuilderCore value="${a} == 1" onChange={onChange} />)

      expectModeValue('visual')

      rerender(<ExpressionBuilderCore value="${b} > 5" onChange={onChange} />)

      expectModeValue('visual')
    })

    it('preserves current mode when external value changes to empty', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      const { rerender } = render(<ExpressionBuilderCore value='${status} == "active"' onChange={onChange} />)

      await selectMode(user, 'raw')
      expectModeValue('raw')

      rerender(<ExpressionBuilderCore value="" onChange={onChange} />)

      expectModeValue('raw')
    })
  })
})
