import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { DRAG_TYPE_CONTEXT, DRAG_TYPE_FIELD, DROP_TARGET_OUTLINE } from '../utils/dragTypes'

import { ExpressionFormField } from './ExpressionFormField'

describe('ExpressionFormField', () => {
  it('renders text input with default placeholder', () => {
    render(<ExpressionFormField id="test-field" label="Value" value="" onChange={vi.fn()} />)

    expect(screen.getByPlaceholderText('Enter or drag and drop value')).toBeInTheDocument()
  })

  it('accepts plain text values and calls onChange', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()
    render(<ExpressionFormField id="test-field" label="Value" value="" onChange={handleChange} />)

    const input = screen.getByRole('textbox', { name: 'Value' })
    await user.type(input, 'hello')

    expect(handleChange).toHaveBeenCalledWith('h')
    expect(handleChange).toHaveBeenCalledTimes(5)
  })

  it('accepts expression syntax as valid input', () => {
    render(
      <ExpressionFormField
        id="test-field"
        label="Value"
        value="${['Schedule trigger'].item.json['Day of the month']}"
        onChange={vi.fn()}
      />
    )

    expect(screen.queryByText('Invalid syntax')).not.toBeInTheDocument()
  })

  it('shows "Invalid syntax" error when expression has unbalanced brackets', () => {
    render(<ExpressionFormField id="test-field" label="Value" value="${['node'].item" onChange={vi.fn()} />)

    expect(screen.getByText('Invalid syntax')).toBeInTheDocument()
  })

  it('does not show error for empty field', () => {
    render(<ExpressionFormField id="test-field" label="Value" value="" onChange={vi.fn()} />)

    expect(screen.queryByText('Invalid syntax')).not.toBeInTheDocument()
  })

  it('does not show error for plain text (non-expression values)', () => {
    render(<ExpressionFormField id="test-field" label="Value" value="just some plain text" onChange={vi.fn()} />)

    expect(screen.queryByText('Invalid syntax')).not.toBeInTheDocument()
  })

  it('shows no error for well-formed expression', () => {
    render(
      <ExpressionFormField id="test-field" label="Value" value="${['node'].item.json['field']}" onChange={vi.fn()} />
    )

    expect(screen.queryByText('Invalid syntax')).not.toBeInTheDocument()
  })

  it('renders with custom label prop', () => {
    render(<ExpressionFormField id="custom-field" label="Custom Label" value="" onChange={vi.fn()} />)

    expect(screen.getByRole('textbox', { name: 'Custom Label' })).toBeInTheDocument()
  })

  it('accepts drop event and populates with expression from field drag data', () => {
    const onChange = vi.fn()
    render(<ExpressionFormField id="test-field" label="Value" value="" onChange={onChange} />)

    const input = screen.getByRole('textbox', { name: 'Value' })

    const dragData = {
      type: DRAG_TYPE_FIELD,
      nodeId: 'schedule_trigger',
      fieldPath: ['Day of the month'],
    }

    fireEvent.drop(input, {
      dataTransfer: {
        getData: () => JSON.stringify(dragData),
      },
    })

    expect(onChange).toHaveBeenCalledWith('${schedule_trigger.Day of the month}')
  })

  it('accepts drop event from context variable drag data', () => {
    const onChange = vi.fn()
    render(<ExpressionFormField id="test-field" label="Value" value="" onChange={onChange} />)

    const input = screen.getByRole('textbox', { name: 'Value' })

    const dragData = {
      type: DRAG_TYPE_CONTEXT,
      contextPath: '$now',
    }

    fireEvent.drop(input, {
      dataTransfer: {
        getData: () => JSON.stringify(dragData),
      },
    })

    expect(onChange).toHaveBeenCalledWith('${$now}')
  })

  it('shows highlight state during dragOver', () => {
    render(<ExpressionFormField id="test-field" label="Value" value="" onChange={vi.fn()} />)

    const input = screen.getByRole('textbox', { name: 'Value' })

    fireEvent.dragOver(input, {
      dataTransfer: { types: ['application/json'] },
    })

    // Assert on the literal inline style rather than toHaveStyle(): getComputedStyle can't
    // resolve var() (happy-dom does not perform real CSS cascade), so it isn't a
    // meaningful check for DROP_TARGET_OUTLINE's outlineColor token.
    expect(input.style.outlineWidth).toBe(DROP_TARGET_OUTLINE.outlineWidth)
    expect(input.style.outlineStyle).toBe(DROP_TARGET_OUTLINE.outlineStyle)
    expect(input.style.outlineColor).toBe(DROP_TARGET_OUTLINE.outlineColor)
  })

  it('removes highlight state on dragLeave', () => {
    render(<ExpressionFormField id="test-field" label="Value" value="" onChange={vi.fn()} />)

    const input = screen.getByRole('textbox', { name: 'Value' })

    fireEvent.dragOver(input, {
      dataTransfer: { types: ['application/json'] },
    })

    fireEvent.dragLeave(input)

    expect(input.style.outlineWidth).toBe('')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExpressionFormField id="test-field" label="Value" value="" onChange={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when showing error', async () => {
    const { container } = render(
      <ExpressionFormField id="test-field" label="Value" value="${['node'].item" onChange={vi.fn()} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('shows external error prop instead of internal validation', () => {
    render(
      <ExpressionFormField
        id="test-field"
        label="Value"
        value="some value"
        onChange={vi.fn()}
        error="Field is required"
      />
    )

    expect(screen.getByText('Field is required')).toBeInTheDocument()
  })

  it('shows "Invalid syntax" for empty expression ${}', () => {
    render(<ExpressionFormField id="test-field" label="Value" value="${}" onChange={vi.fn()} />)

    expect(screen.getByText('Invalid syntax')).toBeInTheDocument()
  })
})
