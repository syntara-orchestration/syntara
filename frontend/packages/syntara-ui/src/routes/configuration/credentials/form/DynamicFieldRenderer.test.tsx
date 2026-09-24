import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { SynForm } from '../../../../components/forms/SynForm'
import { renderWithForm } from '../../../../test/renderWithForm'

import { credentialFormSchema } from './credentialFormSchema'
import type { FieldDefinition } from './DynamicFieldRenderer'
import { DynamicFieldRenderer } from './DynamicFieldRenderer'

const defaultFormValues = {
  name: '',
  description: '',
  project_id: '',
  credential_type_id: '',
  inputs: {} as Record<string, unknown>,
}

function renderDynamicField(
  field: FieldDefinition,
  inputs: Record<string, unknown> = {},
  options?: { isRequired?: boolean; isEditMode?: boolean }
) {
  return renderWithForm(
    {
      schema: credentialFormSchema,
      defaultValues: { ...defaultFormValues, inputs },
    },
    (form) => (
      <SynForm form={form}>
        <DynamicFieldRenderer field={field} isRequired={options?.isRequired} isEditMode={options?.isEditMode} />
      </SynForm>
    )
  )
}

describe('DynamicFieldRenderer', () => {
  const textField: FieldDefinition = {
    id: 'host',
    label: 'Host',
    type: 'string',
    help_text: 'Server hostname',
  }

  const secretField: FieldDefinition = {
    id: 'token',
    label: 'Token',
    type: 'string',
    secret: true,
    help_text: 'Bearer token value',
  }

  const booleanField: FieldDefinition = {
    id: 'verify_ssl',
    label: 'Verify SSL',
    type: 'boolean',
    help_text: 'Enable SSL verification',
  }

  const choicesField: FieldDefinition = {
    id: 'provider',
    label: 'Provider',
    type: 'string',
    choices: ['openai', 'anthropic', 'azure'],
    help_text: 'LLM provider',
  }

  const multilineField: FieldDefinition = {
    id: 'ssh_key',
    label: 'SSH Key',
    type: 'string',
    multiline: true,
    help_text: 'Private key content',
  }

  it('renders a text input for string fields', () => {
    renderDynamicField(textField, { host: 'example.com' })

    expect(screen.getByRole('textbox', { name: 'Host' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('example.com')).toBeInTheDocument()
  })

  it('renders help icon when help_text is provided', () => {
    renderDynamicField(textField)

    expect(screen.getByRole('button', { name: 'More info for Host' })).toBeInTheDocument()
  })

  it('updates text input value on change', async () => {
    const user = userEvent.setup()
    renderDynamicField(textField)

    await user.type(screen.getByRole('textbox', { name: 'Host' }), 'a')

    expect(screen.getByDisplayValue('a')).toBeInTheDocument()
  })

  it('renders a password input for secret fields', () => {
    renderDynamicField(secretField, { token: 'my-secret' })

    const input = screen.getByLabelText('Token', { selector: 'input' })
    expect(input).toHaveAttribute('type', 'password')
  })

  it('toggles password visibility', async () => {
    const user = userEvent.setup()
    renderDynamicField(secretField, { token: 'my-secret' })

    const toggleButton = screen.getByRole('button', { name: 'Show secret' })
    await user.click(toggleButton)

    expect(screen.getByLabelText('Token', { selector: 'input' })).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: 'Hide secret' })).toBeInTheDocument()
  })

  it('renders a switch for boolean fields', () => {
    renderDynamicField(booleanField, { verify_ssl: true })

    expect(screen.getByText('Enabled')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More info for Verify SSL' })).toBeInTheDocument()
  })

  it('updates boolean value on toggle', async () => {
    const user = userEvent.setup()
    renderDynamicField(booleanField, { verify_ssl: true })

    const switchInput = screen.getByRole('switch')
    await user.click(switchInput)

    expect(switchInput).not.toBeChecked()
  })

  it('renders a select for choices fields', () => {
    renderDynamicField(choicesField, { provider: 'openai' })

    expect(screen.getByRole('button', { name: 'Provider' })).toHaveTextContent('openai')
  })

  it('opens a choices menu with many options', async () => {
    const user = userEvent.setup()
    const longChoicesField: FieldDefinition = {
      ...choicesField,
      choices: Array.from({ length: 20 }, (_, i) => `choice-${i + 1}`),
    }
    renderDynamicField(longChoicesField)

    await user.click(screen.getByRole('button', { name: 'Provider' }))

    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'choice-1' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'choice-20' })).toBeInTheDocument()
  })

  it('renders a textarea for multiline fields', () => {
    renderDynamicField(multilineField, { ssh_key: 'key-content' })

    const textarea = screen.getByRole('textbox', { name: 'SSH Key' })
    expect(textarea.tagName).toBe('TEXTAREA')
  })

  it('shows required indicator when isRequired is true', () => {
    renderDynamicField(textField, {}, { isRequired: true })

    expect(screen.getByRole('textbox', { name: 'Host' })).toBeInTheDocument()
  })

  it('shows placeholder dots for encrypted values in edit mode', () => {
    renderDynamicField(secretField, { token: '$encrypted$' }, { isEditMode: true })

    const input = screen.getByLabelText('Token', { selector: 'input' })
    expect(input).toHaveAttribute('placeholder', '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022')
  })
})
