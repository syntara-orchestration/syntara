import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { renderWithForm } from '../../test/renderWithForm'

import { SynSwitchField } from './SynSwitchField'

const schema = z.object({
  enabled: z.boolean().refine((value) => value, 'Enable feature is required'),
})
type FormData = z.infer<typeof schema>

describe('SynSwitchField', () => {
  it('renders switch with label', () => {
    renderWithForm<FormData>({ schema, defaultValues: { enabled: false } }, ({ control }) => (
      <SynSwitchField name="enabled" control={control} label="Enable feature" />
    ))

    expect(screen.getByRole('switch', { name: 'Enable feature' })).toBeInTheDocument()
  })

  it('toggles value when clicked', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { enabled: false } }, ({ control }) => (
      <SynSwitchField name="enabled" control={control} label="Enable feature" />
    ))

    const toggle = screen.getByRole('switch', { name: 'Enable feature' })
    expect(toggle).not.toBeChecked()

    await user.click(toggle)

    expect(toggle).toBeChecked()
  })

  it('shows hint text when provided', () => {
    renderWithForm<FormData>({ schema, defaultValues: { enabled: false } }, ({ control }) => (
      <SynSwitchField name="enabled" control={control} label="Enable feature" hint="Turn on to allow access." />
    ))

    expect(screen.getByText('Turn on to allow access.')).toBeInTheDocument()
  })

  it('turns the switch off when clicked again', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { enabled: true } }, ({ control }) => (
      <SynSwitchField name="enabled" control={control} label="Enable feature" />
    ))

    const toggle = screen.getByRole('switch', { name: 'Enable feature' })
    expect(toggle).toBeChecked()

    await user.click(toggle)

    expect(toggle).not.toBeChecked()
  })

  it('disables the switch when isDisabled is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { enabled: true } }, ({ control }) => (
      <SynSwitchField name="enabled" control={control} label="Enable feature" isDisabled />
    ))

    expect(screen.getByRole('switch', { name: 'Enable feature' })).toBeDisabled()
  })

  it('uses a custom field id', () => {
    renderWithForm<FormData>({ schema, defaultValues: { enabled: false } }, ({ control }) => (
      <SynSwitchField name="enabled" control={control} label="Enable feature" fieldId="custom-enabled" />
    ))

    expect(screen.getByRole('switch', { name: 'Enable feature' })).toHaveAttribute('id', 'custom-enabled')
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderWithForm<FormData>({ schema, defaultValues: { enabled: true } }, ({ control }) => (
      <SynSwitchField name="enabled" control={control} label="Enable feature" />
    ))

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { enabled: false } },
      ({ control, handleSubmit }) => (
        <>
          <SynSwitchField name="enabled" control={control} label="Enable feature" />
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Enable feature is required')

    expect(await axe(container)).toHaveNoViolations()
  })
})
