import { fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { renderWithForm } from '../../test/renderWithForm'
import { DRAG_TYPE_CONTEXT } from '../expressions/expressionFieldDrag'

import { SynExpressionField } from './SynExpressionField'

const schema = z.object({
  expression: z.string().min(1, 'Expression is required'),
})
type FormData = z.infer<typeof schema>

describe('SynExpressionField', () => {
  it('renders label and input', () => {
    renderWithForm<FormData>({ schema, defaultValues: { expression: '' } }, ({ control }) => (
      <SynExpressionField name="expression" control={control} label="Condition" />
    ))

    expect(screen.getByText('Condition')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Condition' })).toBeInTheDocument()
  })

  it('shows syntax validation for invalid expressions', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { expression: '' } }, ({ control }) => (
      <SynExpressionField name="expression" control={control} label="Condition" />
    ))

    await user.click(screen.getByRole('textbox', { name: 'Condition' }))
    await user.paste('${}')

    expect(await screen.findByText('Invalid syntax')).toBeInTheDocument()
  })

  it('shows hint text when provided', () => {
    renderWithForm<FormData>({ schema, defaultValues: { expression: '' } }, ({ control }) => (
      <SynExpressionField
        name="expression"
        control={control}
        label="Condition"
        hint="Drag fields from the canvas into this input."
      />
    ))

    expect(screen.getByText('Drag fields from the canvas into this input.')).toBeInTheDocument()
  })

  it('disables the input when isDisabled is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { expression: '' } }, ({ control }) => (
      <SynExpressionField name="expression" control={control} label="Condition" isDisabled />
    ))

    expect(screen.getByRole('textbox', { name: 'Condition' })).toBeDisabled()
  })

  it('accepts drag-and-drop context expressions', () => {
    renderWithForm<FormData>({ schema, defaultValues: { expression: '' } }, ({ control }) => (
      <SynExpressionField name="expression" control={control} label="Condition" />
    ))

    const input = screen.getByRole('textbox', { name: 'Condition' })
    fireEvent.drop(input, {
      dataTransfer: {
        getData: () =>
          JSON.stringify({
            type: DRAG_TYPE_CONTEXT,
            contextPath: '$now',
          }),
      },
    })

    expect(input).toHaveValue('${$now}')
  })

  it('coerces non-string form values to an empty input value', () => {
    const looseSchema = z.object({
      expression: z.any(),
    })

    renderWithForm({ schema: looseSchema, defaultValues: { expression: 42 } }, ({ control }) => (
      <SynExpressionField name="expression" control={control} label="Condition" />
    ))

    expect(screen.getByRole('textbox', { name: 'Condition' })).toHaveValue('')
  })

  it('uses a custom placeholder and field id', () => {
    renderWithForm<FormData>({ schema, defaultValues: { expression: '' } }, ({ control }) => (
      <SynExpressionField
        name="expression"
        control={control}
        label="Condition"
        placeholder="Enter a condition"
        fieldId="custom-condition"
      />
    ))

    expect(screen.getByPlaceholderText('Enter a condition')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Condition' })).toHaveAttribute('id', 'custom-condition')
  })

  it('shows required validation on submit', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { expression: '' } }, ({ control, handleSubmit }) => (
      <>
        <SynExpressionField name="expression" control={control} label="Condition" isRequired />
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Expression is required')).toBeInTheDocument()
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { expression: '${node.output}' } },
      ({ control }) => <SynExpressionField name="expression" control={control} label="Condition" />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { expression: '' } },
      ({ control, handleSubmit }) => (
        <>
          <SynExpressionField name="expression" control={control} label="Condition" isRequired />
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Expression is required')

    expect(await axe(container)).toHaveNoViolations()
  })
})
