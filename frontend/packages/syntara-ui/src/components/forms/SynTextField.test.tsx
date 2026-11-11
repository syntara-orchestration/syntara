import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { renderWithForm } from '../../test/renderWithForm'
import { detachPromise } from '../../utils/detachPromise'

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
    const input = screen.getByRole('textbox', { name: 'Group name' })
    expect(input).toBeInTheDocument()
    expect(input).not.toHaveAttribute('aria-describedby')
  })

  it('shows placeholder text', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" placeholder="Enter group name" />
    ))

    expect(screen.getByPlaceholderText('Enter group name')).toBeInTheDocument()
  })

  it('focuses the input when React Hook Form calls setFocus with an explicit control', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control, setFocus }) => (
      <>
        <SynTextField name="name" control={control} label="Group name" />
        <button type="button" onClick={() => setFocus('name')}>
          Focus name
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Focus name' }))

    expect(screen.getByRole('textbox', { name: 'Group name' })).toHaveFocus()
  })

  it('focuses the first invalid input from form context and advances after it is corrected', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: 'invalid' } }, (form) => (
      <FormProvider {...form}>
        <SynTextField name="name" label="Group name" />
        <SynTextField name="email" label="Email" type="email" />
        <button type="button" onClick={form.handleSubmit(onSubmit)}>
          Submit
        </button>
      </FormProvider>
    ))
    const name = screen.getByRole('textbox', { name: 'Group name' })
    const email = screen.getByRole('textbox', { name: 'Email' })
    const submit = screen.getByRole('button', { name: 'Submit' })

    await user.click(submit)
    await screen.findByText('Name is required')
    await waitFor(() => expect(name).toHaveFocus())
    expect(name).toHaveAccessibleDescription(/Name is required/)
    expect(onSubmit).not.toHaveBeenCalled()

    await user.type(name, 'my-group')
    await user.click(submit)
    await waitFor(() => expect(email).toHaveFocus())
    expect(email).toHaveAccessibleDescription(/Invalid email/)
    expect(onSubmit).not.toHaveBeenCalled()

    await user.clear(email)
    await user.type(email, 'user@example.com')
    await user.click(submit)
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ name: 'my-group', email: 'user@example.com' }, expect.anything())
    )
  })

  it('shows required indicator', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" isRequired />
    ))

    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('marks the input as required when isRequired is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" isRequired />
    ))

    const input = screen.getByRole('textbox', { name: 'Group name' })
    expect(input).toBeRequired()
    expect(input).toHaveAttribute('aria-required', 'true')
  })

  it('shows hint text when valid', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" hint="Lowercase letters and hyphens only" />
    ))

    const input = screen.getByRole('textbox', { name: 'Group name' })
    expect(screen.getByText('Lowercase letters and hyphens only')).toBeInTheDocument()
    const describedBy = input.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(input).toHaveAccessibleDescription('Lowercase letters and hyphens only')
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

    const input = screen.getByRole('textbox', { name: 'Group name' })
    expect(screen.getByText('Enter a name')).toBeInTheDocument()
    const describedBy = input.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Name is required')).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-describedby', describedBy)
    expect(input).toHaveAccessibleDescription(/Name is required/)
    expect(screen.queryByText('Enter a name')).not.toBeInTheDocument()
  })

  it('omits aria-describedby when an error has no rendered message', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control, setError }) => (
      <>
        <SynTextField name="name" control={control} label="Group name" hint="Enter a name" />
        <button type="button" onClick={() => setError('name', { type: 'manual' })}>
          Set error without a message
        </button>
      </>
    ))

    const input = screen.getByRole('textbox', { name: 'Group name' })
    await user.click(screen.getByRole('button', { name: 'Set error without a message' }))

    expect(input).not.toHaveAttribute('aria-describedby')
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

  it('coerces number input values to numbers for zod number fields', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const numberSchema = z.object({ count: z.number().int().positive().optional() })

    renderWithForm({ schema: numberSchema, defaultValues: {} }, ({ control, handleSubmit }) => (
      <>
        <SynTextField name="count" control={control} label="Count" type="number" min={1} />
        <button type="button" onClick={handleSubmit(onSubmit)}>
          Submit
        </button>
      </>
    ))

    const input = screen.getByRole('spinbutton', { name: 'Count' })
    await user.type(input, '300')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onSubmit).toHaveBeenCalledWith({ count: 300 }, expect.anything())
  })

  it('submits undefined when a number input is cleared without blur', async () => {
    // Invokes handleSubmit directly while the input stays focused (no submit button click / blur).
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const numberSchema = z.object({ count: z.number().optional() })
    let submitWhileFocused: (() => void) | undefined

    renderWithForm({ schema: numberSchema, defaultValues: { count: 300 } }, ({ control, handleSubmit }) => {
      submitWhileFocused = () => {
        detachPromise(Promise.resolve(handleSubmit(onSubmit)()))
      }
      return <SynTextField name="count" control={control} label="Count" type="number" />
    })

    const input = screen.getByRole('spinbutton', { name: 'Count' })
    await user.clear(input)
    expect(input).toHaveFocus()

    submitWhileFocused?.()

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalled()
      expect(onSubmit.mock.calls[0]?.[0]).toEqual({ count: undefined })
    })
  })

  it('allows typing decimal values without stripping the decimal point mid-edit', async () => {
    const user = userEvent.setup()
    const numberSchema = z.object({ rate: z.number().positive().optional() })

    renderWithForm({ schema: numberSchema, defaultValues: {} }, ({ control }) => (
      <SynTextField name="rate" control={control} label="Rate" type="number" step={0.1} />
    ))

    const input = screen.getByRole('spinbutton', { name: 'Rate' })
    await user.type(input, '1.5')
    expect(input).toHaveValue(1.5)
  })

  it('forwards autoComplete to the input', () => {
    renderWithForm<FormData>({ schema, defaultValues: { name: '', email: '' } }, ({ control }) => (
      <SynTextField name="name" control={control} label="Group name" autoComplete="off" />
    ))

    expect(screen.getByRole('textbox', { name: 'Group name' })).toHaveAttribute('autocomplete', 'off')
  })

  it('has no accessibility violations with helper text', async () => {
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { name: '', email: '' } },
      ({ control }) => <SynTextField name="name" control={control} label="Group name" hint="Enter a name" isRequired />
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
