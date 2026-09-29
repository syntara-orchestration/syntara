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
      </SynForm>
    ))

    expect(screen.getByRole('textbox', { name: 'Username' })).toBeInTheDocument()
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

    expect(screen.getByText('Enter your username')).toBeInTheDocument()
  })

  it('shows a validation error and hides the hint after failed submit', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { username: '' } }, ({ control, handleSubmit }) => (
      <>
        <SynFormField name="username" control={control} label="Username" hint="Enter your username">
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
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Username is required')).toBeInTheDocument()
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
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Username is required')

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
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(screen.queryByText('Username is required')).not.toBeInTheDocument()
    expect(screen.queryByText('Enter your username')).not.toBeInTheDocument()
  })
})
