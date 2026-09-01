import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { FieldDefinition } from './DynamicFieldRenderer'
import { DynamicFieldRenderer } from './DynamicFieldRenderer'

describe('DynamicFieldRenderer', () => {
  const onChange = vi.fn()

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
    render(<DynamicFieldRenderer field={textField} value="example.com" onChange={onChange} />)

    expect(screen.getByRole('textbox', { name: 'Host' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('example.com')).toBeInTheDocument()
  })

  it('renders help icon when help_text is provided', () => {
    render(<DynamicFieldRenderer field={textField} value="" onChange={onChange} />)

    expect(screen.getByRole('button', { name: 'Host help' })).toBeInTheDocument()
  })

  it('calls onChange when text input changes', async () => {
    const user = userEvent.setup()
    render(<DynamicFieldRenderer field={textField} value="" onChange={onChange} />)

    await user.type(screen.getByRole('textbox', { name: 'Host' }), 'a')

    expect(onChange).toHaveBeenCalledWith('host', 'a')
  })

  it('renders a password input for secret fields', () => {
    render(<DynamicFieldRenderer field={secretField} value="my-secret" onChange={onChange} />)

    const input = screen.getByLabelText('Token', { selector: 'input' })
    expect(input).toHaveAttribute('type', 'password')
  })

  it('toggles password visibility', async () => {
    const user = userEvent.setup()
    render(<DynamicFieldRenderer field={secretField} value="my-secret" onChange={onChange} />)

    const toggleButton = screen.getByRole('button', { name: 'Show secret' })
    await user.click(toggleButton)

    expect(screen.getByLabelText('Token', { selector: 'input' })).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: 'Hide secret' })).toBeInTheDocument()
  })

  it('renders a switch for boolean fields', () => {
    render(<DynamicFieldRenderer field={booleanField} value={true} onChange={onChange} />)

    expect(screen.getByText('Enabled')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Verify SSL help' })).toBeInTheDocument()
  })

  it('calls onChange for boolean toggle', async () => {
    const user = userEvent.setup()
    render(<DynamicFieldRenderer field={booleanField} value={true} onChange={onChange} />)

    const switchInput = screen.getByRole('switch')
    await user.click(switchInput)

    expect(onChange).toHaveBeenCalledWith('verify_ssl', false)
  })

  it('renders a select for choices fields', () => {
    render(<DynamicFieldRenderer field={choicesField} value="openai" onChange={onChange} />)

    expect(screen.getByRole('button', { name: 'Provider' })).toHaveTextContent('openai')
  })

  it('opens a choices menu with many options', async () => {
    const user = userEvent.setup()
    const longChoicesField: FieldDefinition = {
      ...choicesField,
      choices: Array.from({ length: 20 }, (_, i) => `choice-${i + 1}`),
    }
    render(<DynamicFieldRenderer field={longChoicesField} value="" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Provider' }))

    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'choice-1' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'choice-20' })).toBeInTheDocument()
  })

  it('renders a textarea for multiline fields', () => {
    render(<DynamicFieldRenderer field={multilineField} value="key-content" onChange={onChange} />)

    const textarea = screen.getByRole('textbox', { name: 'SSH Key' })
    expect(textarea.tagName).toBe('TEXTAREA')
  })

  it('shows required indicator when isRequired is true', () => {
    render(<DynamicFieldRenderer field={textField} value="" onChange={onChange} isRequired />)

    expect(screen.getByRole('textbox', { name: 'Host' })).toBeInTheDocument()
  })

  it('shows placeholder dots for encrypted values in edit mode', () => {
    render(<DynamicFieldRenderer field={secretField} value="$encrypted$" onChange={onChange} isEditMode />)

    const input = screen.getByLabelText('Token', { selector: 'input' })
    expect(input).toHaveAttribute('placeholder', '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022')
  })

  it('coerces numeric field values to display strings', () => {
    render(<DynamicFieldRenderer field={textField} value={443} onChange={onChange} />)

    expect(screen.getByDisplayValue('443')).toBeInTheDocument()
  })

  it('coerces boolean field values to display strings', () => {
    render(<DynamicFieldRenderer field={textField} value={false} onChange={onChange} />)

    expect(screen.getByDisplayValue('false')).toBeInTheDocument()
  })

  it('renders an empty text input when the value is null', () => {
    render(<DynamicFieldRenderer field={textField} value={null} onChange={onChange} />)

    expect(screen.getByRole('textbox', { name: 'Host' })).toHaveValue('')
  })

  it('rejects object values instead of stringifying them', () => {
    render(<DynamicFieldRenderer field={textField} value={{ host: 'example.com' }} onChange={onChange} />)

    expect(screen.getByRole('textbox', { name: 'Host' })).toHaveValue('')
    expect(screen.queryByDisplayValue('[object Object]')).not.toBeInTheDocument()
  })

  it('rejects array values instead of stringifying them', () => {
    render(<DynamicFieldRenderer field={multilineField} value={['line-1', 'line-2']} onChange={onChange} />)

    expect(screen.getByRole('textbox', { name: 'SSH Key' })).toHaveValue('')
  })

  it('shows field-level validation errors', () => {
    render(<DynamicFieldRenderer field={textField} value="" onChange={onChange} error="Host is required" />)

    expect(screen.getByText('Host is required')).toBeInTheDocument()
  })

  it('marks a secret as touched so the encrypted placeholder clears after editing', async () => {
    const user = userEvent.setup()
    render(<DynamicFieldRenderer field={secretField} value="$encrypted$" onChange={onChange} isEditMode />)

    const input = screen.getByLabelText('Token', { selector: 'input' })
    expect(input).toHaveAttribute('placeholder', '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022')

    await user.type(input, 'n')

    expect(onChange).toHaveBeenCalledWith('token', 'n')
    expect(input).not.toHaveAttribute('placeholder', '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022')
  })

  it('selects a choices option and notifies onChange', async () => {
    const user = userEvent.setup()
    render(<DynamicFieldRenderer field={choicesField} value="" onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Provider' }))
    await user.click(screen.getByRole('option', { name: 'anthropic' }))

    expect(onChange).toHaveBeenCalledWith('provider', 'anthropic')
  })
})
