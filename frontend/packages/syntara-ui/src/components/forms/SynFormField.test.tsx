import { TextInput } from '@patternfly/react-core'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { renderWithForm } from '../../test/renderWithForm'
import { FieldHelpPopover } from '../FieldHelpPopover'

import { SynForm } from './SynForm'
import { SynFormField } from './SynFormField'
import { SynSwitchField } from './SynSwitchField'
import { SynTextField } from './SynTextField'

const schema = z.object({ username: z.string().min(1, 'Username is required') })
type FormData = z.infer<typeof schema>

describe('SynFormField', () => {
  it('omits control when wrapped in SynForm', () => {
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, (form) => (
      <SynForm form={form}>
        <SynFormField<FormData, 'username'> name="username" label="Username">
          {({ field, describedBy }) => (
            <TextInput
              id="username"
              aria-label="Username"
              aria-describedby={describedBy}
              value={field.value ?? ''}
              onChange={field.onChange}
              name={field.name}
            />
          )}
        </SynFormField>
      </SynForm>
    ))

    const input = screen.getByRole('textbox', { name: 'Username' })
    expect(input).toBeInTheDocument()
    expect(input).not.toHaveAttribute('aria-describedby')
  })

  it('renders the label', () => {
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control }) => (
      <SynFormField name="username" control={control} label="Username">
        {({ field, fieldState }) => (
          <TextInput
            id="username"
            aria-label="Username"
            validated={fieldState.error ? 'error' : 'default'}
            value={field.value ?? ''}
            onChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
          />
        )}
      </SynFormField>
    ))

    expect(screen.getByText('Username')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Username' })).toBeInTheDocument()
  })

  it('shows a required indicator when isRequired is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control }) => (
      <SynFormField name="username" control={control} label="Username" isRequired>
        {({ field }) => (
          <TextInput
            id="username"
            aria-label="Username"
            value={field.value ?? ''}
            onChange={field.onChange}
            name={field.name}
          />
        )}
      </SynFormField>
    ))

    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('shows a hint when there is no error', () => {
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control }) => (
      <SynFormField name="username" control={control} label="Username" hint="Enter your username">
        {({ field, describedBy }) => (
          <TextInput
            id="username"
            aria-label="Username"
            aria-describedby={describedBy}
            value={field.value ?? ''}
            onChange={field.onChange}
            name={field.name}
          />
        )}
      </SynFormField>
    ))

    const input = screen.getByRole('textbox', { name: 'Username' })
    expect(screen.getByText('Enter your username')).toBeInTheDocument()
    const describedBy = input.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(input).toHaveAccessibleDescription('Enter your username')
  })

  it('generates unique helper IDs that do not collide with field IDs', () => {
    const multiFieldSchema = z.object({ first: z.string(), second: z.string() })
    renderWithForm({ schema: multiFieldSchema, defaultValues: { first: '', second: '' } }, ({ control }) => (
      <>
        <SynFormField name="first" control={control} label="First field" fieldId="field" hint="First hint">
          {({ field, describedBy }) => (
            <TextInput
              id="field"
              aria-label="First field"
              aria-describedby={describedBy}
              value={field.value ?? ''}
              onChange={field.onChange}
              name={field.name}
            />
          )}
        </SynFormField>
        <SynFormField
          name="second"
          control={control}
          label="Second field"
          fieldId="field-helper-text"
          hint="Second hint"
        >
          {({ field, describedBy }) => (
            <TextInput
              id="field-helper-text"
              aria-label="Second field"
              aria-describedby={describedBy}
              value={field.value ?? ''}
              onChange={field.onChange}
              name={field.name}
            />
          )}
        </SynFormField>
      </>
    ))

    const firstInput = screen.getByRole('textbox', { name: 'First field' })
    const secondInput = screen.getByRole('textbox', { name: 'Second field' })
    expect(screen.getByText('First hint')).toBeInTheDocument()
    expect(screen.getByText('Second hint')).toBeInTheDocument()
    const firstDescriptionId = firstInput.getAttribute('aria-describedby')
    const secondDescriptionId = secondInput.getAttribute('aria-describedby')
    expect(firstDescriptionId).toBeTruthy()
    expect(secondDescriptionId).toBeTruthy()

    expect(firstInput).toHaveAccessibleDescription('First hint')
    expect(secondInput).toHaveAccessibleDescription('Second hint')
    expect(firstDescriptionId).not.toBe(firstInput.id)
    expect(firstDescriptionId).not.toBe(secondInput.id)
    expect(secondDescriptionId).not.toBe(firstInput.id)
    expect(secondDescriptionId).not.toBe(secondInput.id)
    expect(firstDescriptionId).not.toBe(secondDescriptionId)
  })

  it('shows a validation error and hides the hint after failed submit', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control, handleSubmit }) => (
      <>
        <SynFormField name="username" control={control} label="Username" hint="Enter your username">
          {({ field, fieldState, describedBy }) => (
            <TextInput
              id="username"
              aria-label="Username"
              aria-describedby={describedBy}
              validated={fieldState.error ? 'error' : 'default'}
              value={field.value ?? ''}
              onChange={field.onChange}
              onBlur={field.onBlur}
              name={field.name}
            />
          )}
        </SynFormField>
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    const input = screen.getByRole('textbox', { name: 'Username' })
    expect(screen.getByText('Enter your username')).toBeInTheDocument()
    const describedBy = input.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Username is required')).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-describedby', describedBy)
    expect(input).toHaveAccessibleDescription(/Username is required/)
    expect(screen.queryByText('Enter your username')).not.toBeInTheDocument()
  })

  it('does not describe the field when an error has no rendered message', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control, setError }) => (
      <>
        <SynFormField name="username" control={control} label="Username" hint="Enter your username">
          {({ field, describedBy }) => (
            <TextInput
              id="username"
              aria-label="Username"
              aria-describedby={describedBy}
              value={field.value ?? ''}
              onChange={field.onChange}
              name={field.name}
            />
          )}
        </SynFormField>
        <button type="button" onClick={() => setError('username', { type: 'manual' })}>
          Set error without a message
        </button>
      </>
    ))

    const input = screen.getByRole('textbox', { name: 'Username' })
    await user.click(screen.getByRole('button', { name: 'Set error without a message' }))

    expect(input).not.toHaveAttribute('aria-describedby')
    expect(screen.queryByText('Enter your username')).not.toBeInTheDocument()
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control }) => (
      <SynFormField name="username" control={control} label="Username">
        {({ field }) => (
          <TextInput
            id="username"
            aria-label="Username"
            value={field.value ?? ''}
            onChange={field.onChange}
            name={field.name}
          />
        )}
      </SynFormField>
    ))

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { username: '' } },
      ({ control, handleSubmit }) => (
        <>
          <SynFormField name="username" control={control} label="Username" isRequired>
            {({ field, fieldState, describedBy }) => (
              <TextInput
                id="username"
                aria-label="Username"
                aria-describedby={describedBy}
                validated={fieldState.error ? 'error' : 'default'}
                value={field.value ?? ''}
                onChange={field.onChange}
                onBlur={field.onBlur}
                name={field.name}
              />
            )}
          </SynFormField>
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    expect(await screen.findByText('Username is required')).toBeInTheDocument()
    const input = screen.getByRole('textbox', { name: 'Username' })
    const describedBy = input.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(input).toHaveAccessibleDescription(/Username is required/)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('omits the FormGroup label when hideFormGroupLabel is true', () => {
    const switchSchema = z.object({ enabled: z.boolean() })
    renderWithForm({ schema: switchSchema, defaultValues: { enabled: false } }, ({ control }) => (
      <SynSwitchField name="enabled" control={control} label="Enable feature" />
    ))

    expect(screen.getAllByText('Enable feature')).toHaveLength(1)
    expect(screen.getByRole('switch', { name: 'Enable feature' })).toBeInTheDocument()
  })

  it('shows the FormGroup label for standard text fields', () => {
    renderWithForm({ schema, defaultValues: { username: '' } }, ({ control }) => (
      <SynTextField name="username" control={control} label="Username" />
    ))

    expect(screen.getByText('Username')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Username' })).toBeInTheDocument()
  })

  it('renders label help popover content', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control }) => (
      <SynFormField
        name="username"
        control={control}
        label="Username"
        labelHelp={<FieldHelpPopover headerContent="Username" helpText="Enter your login name." />}
      >
        {({ field }) => (
          <TextInput
            id="username"
            aria-label="Username"
            value={field.value ?? ''}
            onChange={field.onChange}
            name={field.name}
          />
        )}
      </SynFormField>
    ))

    await user.click(screen.getByRole('button', { name: 'More info for Username' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Enter your login name.')).toBeInTheDocument()
  })

  it('omits the default footer when hideFooter is true', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control, handleSubmit }) => (
      <>
        <SynFormField name="username" control={control} label="Username" hint="Enter your username" hideFooter>
          {({ field, describedBy }) => (
            <TextInput
              id="username"
              aria-label="Username"
              aria-describedby={describedBy}
              value={field.value ?? ''}
              onChange={field.onChange}
              name={field.name}
            />
          )}
        </SynFormField>
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(screen.getByRole('textbox', { name: 'Username' })).not.toHaveAttribute('aria-describedby')
    expect(screen.queryByText('Username is required')).not.toBeInTheDocument()
    expect(screen.queryByText('Enter your username')).not.toBeInTheDocument()
  })
})
