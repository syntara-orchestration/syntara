import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { DRAG_TYPE_CONTEXT, DRAG_TYPE_FIELD } from '../expressions/expressionFieldDrag'

import { ExpressionFieldInput } from './ExpressionFieldInput'

describe('ExpressionFieldInput', () => {
  it('calls onChange when the user types', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpressionFieldInput id="expression" value="" onChange={onChange} />)

    await user.type(screen.getByRole('textbox'), 'hello')

    expect(onChange).toHaveBeenCalled()
  })

  it('shows hint text when there is no error', () => {
    render(<ExpressionFieldInput id="expression" value="" onChange={vi.fn()} hint="Use ${...} syntax" />)

    expect(screen.getByText('Use ${...} syntax')).toBeInTheDocument()
  })

  it('prefers externalError over syntax validation', () => {
    render(<ExpressionFieldInput id="expression" value="${}" onChange={vi.fn()} externalError="Field is required" />)

    expect(screen.getByText('Field is required')).toBeInTheDocument()
    expect(screen.queryByText('Invalid syntax')).not.toBeInTheDocument()
  })

  it('accepts drop event and appends field expression', () => {
    const onChange = vi.fn()
    render(<ExpressionFieldInput id="expression" value="prefix " onChange={onChange} />)

    const input = screen.getByRole('textbox')
    fireEvent.drop(input, {
      dataTransfer: {
        getData: () =>
          JSON.stringify({
            type: DRAG_TYPE_FIELD,
            nodeId: 'schedule_trigger',
            fieldPath: ['Day of the month'],
          }),
      },
    })

    expect(onChange).toHaveBeenCalledWith('prefix ${schedule_trigger.Day of the month}')
  })

  it('accepts drop event and appends context expression', () => {
    const onChange = vi.fn()
    render(<ExpressionFieldInput id="expression" value="" onChange={onChange} />)

    const input = screen.getByRole('textbox')
    fireEvent.drop(input, {
      dataTransfer: {
        getData: () =>
          JSON.stringify({
            type: DRAG_TYPE_CONTEXT,
            contextPath: '$now',
          }),
      },
    })

    expect(onChange).toHaveBeenCalledWith('${$now}')
  })

  it('ignores drop events with invalid drag data', () => {
    const onChange = vi.fn()
    render(<ExpressionFieldInput id="expression" value="" onChange={onChange} />)

    const input = screen.getByRole('textbox')
    fireEvent.drop(input, {
      dataTransfer: {
        getData: () => JSON.stringify({ type: 'unknown' }),
      },
    })

    expect(onChange).not.toHaveBeenCalled()
  })

  it('ignores drop events with malformed JSON', () => {
    const onChange = vi.fn()
    render(<ExpressionFieldInput id="expression" value="" onChange={onChange} />)

    const input = screen.getByRole('textbox')
    fireEvent.drop(input, {
      dataTransfer: {
        getData: () => '{not-json',
      },
    })

    expect(onChange).not.toHaveBeenCalled()
  })

  it('ignores drop events with empty drag payload', () => {
    const onChange = vi.fn()
    render(<ExpressionFieldInput id="expression" value="" onChange={onChange} />)

    const input = screen.getByRole('textbox')
    fireEvent.drop(input, {
      dataTransfer: {
        getData: () => '',
      },
    })

    expect(onChange).not.toHaveBeenCalled()
  })

  it('shows highlight state during dragOver and clears it on dragLeave', () => {
    const onDropTargetChange = vi.fn()
    render(<ExpressionFieldInput id="expression" value="" onChange={vi.fn()} onDropTargetChange={onDropTargetChange} />)

    const input = screen.getByRole('textbox')

    fireEvent.dragOver(input, {
      dataTransfer: { types: ['application/json'] },
    })
    expect(input).toHaveAttribute('data-drop-target', 'active')
    expect(onDropTargetChange).toHaveBeenCalledWith(true)

    fireEvent.dragLeave(input)
    expect(input).toHaveAttribute('data-drop-target', 'inactive')
    expect(onDropTargetChange).toHaveBeenCalledWith(false)
  })

  it('disables the input when isDisabled is true', () => {
    render(<ExpressionFieldInput id="expression" value="" onChange={vi.fn()} isDisabled />)

    expect(screen.getByRole('textbox')).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExpressionFieldInput id="expression" value="" onChange={vi.fn()} />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
