import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { renderWithForm } from '../../test/renderWithForm'

import { SynTextAreaField } from './SynTextAreaField'

const schema = z.object({
  description: z.string().max(2000, 'Description must be 2000 characters or fewer').optional(),
  notes: z.string().min(1, 'Notes are required'),
})
type FormData = z.infer<typeof schema>

describe('SynTextAreaField', () => {
  it('renders label and textarea', () => {
    renderWithForm<FormData>({ schema, defaultValues: { description: '', notes: '' } }, ({ control }) => (
      <SynTextAreaField name="description" control={control} label="Description" />
    ))

    expect(screen.getByText('Description')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Description' })).toBeInTheDocument()
  })

  it('shows placeholder text', () => {
    renderWithForm<FormData>({ schema, defaultValues: { description: '', notes: '' } }, ({ control }) => (
      <SynTextAreaField name="description" control={control} label="Description" placeholder="Enter description" />
    ))

    expect(screen.getByPlaceholderText('Enter description')).toBeInTheDocument()
  })

  it('shows hint text when valid', () => {
    renderWithForm<FormData>({ schema, defaultValues: { description: '', notes: '' } }, ({ control }) => (
      <SynTextAreaField name="description" control={control} label="Description" hint="Up to 2000 characters" />
    ))

    expect(screen.getByText('Up to 2000 characters')).toBeInTheDocument()
  })

  it('shows validation error on submit', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { description: '', notes: '' } }, ({ control, handleSubmit }) => (
      <>
        <SynTextAreaField name="notes" control={control} label="Notes" isRequired />
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Notes are required')).toBeInTheDocument()
  })

  it('disables the textarea when isDisabled is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { description: '', notes: '' } }, ({ control }) => (
      <SynTextAreaField name="description" control={control} label="Description" isDisabled />
    ))

    expect(screen.getByRole('textbox', { name: 'Description' })).toBeDisabled()
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { description: '', notes: '' } },
      ({ control }) => <SynTextAreaField name="description" control={control} label="Description" />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { description: '', notes: '' } },
      ({ control, handleSubmit }) => (
        <>
          <SynTextAreaField name="notes" control={control} label="Notes" isRequired />
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Notes are required')

    expect(await axe(container)).toHaveNoViolations()
  })
})
