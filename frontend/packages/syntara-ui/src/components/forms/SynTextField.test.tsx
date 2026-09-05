import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { renderWithForm } from '../../test/renderWithForm'

import { SynTextField } from './SynTextField'

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  email: z.string().email('Invalid email').optional().or(z.literal('')),
})
type FormData = z.infer<typeof schema>

describe('SynTextField', () => {
  it('renders label and input', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" />
    ))

    expect(screen.getByText('Group name')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Group name' })).toBeInTheDocument()
  })

  it('shows placeholder text', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" placeholder="Enter group name" />
    ))

    expect(screen.getByPlaceholderText('Enter group name')).toBeInTheDocument()
  })

  it('shows required indicator', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" isRequired />
    ))

    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('shows hint text when valid', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" hint="Lowercase letters and hyphens only" />
    ))

    expect(screen.getByText('Lowercase letters and hyphens only')).toBeInTheDocument()
  })

  it('shows validation error on submit and hides hint', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control, handleSubmit }) => (
      <>
        <SynTextField name="name" control={control} label="Group name" hint="Enter a name" />
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Name is required')).toBeInTheDocument()
    expect(screen.queryByText('Enter a name')).not.toBeInTheDocument()
  })

  it('clears validation error after user types a valid value', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control, handleSubmit }) => (
      <>
        <SynTextField name="name" control={control} label="Group name" />
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Name is required')

    await user.type(screen.getByRole('textbox', { name: 'Group name' }), 'my-group')
    await user.tab()

    expect(screen.queryByText('Name is required')).not.toBeInTheDocument()
  })

  it('disables the input when isDisabled is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" isDisabled />
    ))

    expect(screen.getByRole('textbox', { name: 'Group name' })).toBeDisabled()
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { name: '', email: '' } },
      ({ control }) => <SynTextField name="name" control={control} label="Group name" isRequired />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { name: '', email: '' } },
      ({ control, handleSubmit }) => (
        <>
          <SynTextField name="name" control={control} label="Group name" isRequired />
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Name is required')

    expect(await axe(container)).toHaveNoViolations()
  })
})
