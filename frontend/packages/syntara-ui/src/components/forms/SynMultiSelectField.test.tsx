import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { renderWithForm } from '../../test/renderWithForm'

import { SynMultiSelectField } from './SynMultiSelectField'

const schema = z.object({
  roles: z.array(z.string()).min(1, 'Select at least one role'),
})
type FormData = z.infer<typeof schema>

const options = [
  { value: 'admin', label: 'Administrator' },
  { value: 'auditor', label: 'Auditor' },
  { value: 'user', label: 'User' },
]

describe('SynMultiSelectField', () => {
  it('renders label and placeholder', () => {
    renderWithForm<FormData>({ schema, defaultValues: { roles: [] } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} />
    ))

    expect(screen.getByText('Roles')).toBeInTheDocument()
    expect(screen.getByLabelText('Roles')).toHaveTextContent('Select options')
  })

  it('toggles selected values from the menu', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { roles: [] } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} />
    ))

    await user.click(screen.getByLabelText('Roles'))
    await user.click(screen.getByRole('checkbox', { name: 'Administrator' }))
    await user.click(screen.getByRole('checkbox', { name: 'Auditor' }))

    expect(screen.getByLabelText('Roles')).toHaveTextContent('Administrator, Auditor')
  })

  it('deselects a value when its checkbox is clicked again', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { roles: ['admin'] } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} />
    ))

    expect(screen.getByLabelText('Roles')).toHaveTextContent('Administrator')

    await user.click(screen.getByLabelText('Roles'))
    await user.click(screen.getByRole('checkbox', { name: 'Administrator' }))

    expect(screen.getByLabelText('Roles')).toHaveTextContent('Select options')
  })

  it('summarizes three or more selections', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { roles: [] } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} />
    ))

    await user.click(screen.getByLabelText('Roles'))
    await user.click(screen.getByRole('checkbox', { name: 'Administrator' }))
    await user.click(screen.getByRole('checkbox', { name: 'Auditor' }))
    await user.click(screen.getByRole('checkbox', { name: 'User' }))

    expect(screen.getByLabelText('Roles')).toHaveTextContent('3 selected')
  })

  it('disables the select when isDisabled is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { roles: [] } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} isDisabled />
    ))

    expect(screen.getByLabelText('Roles')).toBeDisabled()
  })

  it('uses a custom placeholder when nothing is selected', () => {
    renderWithForm<FormData>({ schema, defaultValues: { roles: [] } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} placeholder="Choose roles" />
    ))

    expect(screen.getByLabelText('Roles')).toHaveTextContent('Choose roles')
  })

  it('shows raw values when selected items are not in the option list', () => {
    renderWithForm<FormData>({ schema, defaultValues: { roles: ['custom-role'] } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} />
    ))

    expect(screen.getByLabelText('Roles')).toHaveTextContent('custom-role')
  })

  it('treats non-array form values as empty selections', () => {
    const looseSchema = z.object({
      roles: z.any(),
    })

    renderWithForm({ schema: looseSchema, defaultValues: { roles: 'admin' } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} />
    ))

    expect(screen.getByLabelText('Roles')).toHaveTextContent('Select options')
  })

  it('shows validation error on submit', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { roles: [] } }, ({ control, handleSubmit }) => (
      <>
        <SynMultiSelectField name="roles" control={control} label="Roles" options={options} isRequired />
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Select at least one role')).toBeInTheDocument()
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderWithForm<FormData>({ schema, defaultValues: { roles: ['admin'] } }, ({ control }) => (
      <SynMultiSelectField name="roles" control={control} label="Roles" options={options} />
    ))

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { roles: [] } },
      ({ control, handleSubmit }) => (
        <>
          <SynMultiSelectField name="roles" control={control} label="Roles" options={options} isRequired />
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Select at least one role')

    expect(await axe(container)).toHaveNoViolations()
  })
})
