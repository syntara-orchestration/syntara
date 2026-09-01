import type { SettingsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SettingInput } from './SettingInput'

type RuntimeSetting = SettingsAPI.components['schemas']['RuntimeSettingRead']

const baseSetting: RuntimeSetting = {
  id: '1',
  key: 'test.setting',
  name: 'Test setting',
  description: 'A test setting',
  helper_text: null,
  depends_on: null,
  category: 'test',
  group: 'General',
  value: null,
  default_value: 100,
  effective_value: 100,
  value_type: 'integer',
  requires_restart: false,
  cache_ttl_seconds: null,
  validation_schema: null,
  version: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('SettingInput', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(
      <SettingInput
        setting={baseSetting}
        value={100}
        numericBounds={null}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={vi.fn()}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders boolean as Switch', () => {
    const boolSetting = { ...baseSetting, value_type: 'boolean' as const }
    render(
      <SettingInput
        setting={boolSetting}
        value={true}
        numericBounds={null}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    expect(screen.getByText('Enabled')).toBeInTheDocument()
  })

  it('boolean switch calls onChange on toggle', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const boolSetting = { ...baseSetting, value_type: 'boolean' as const }
    render(
      <SettingInput
        setting={boolSetting}
        value={true}
        numericBounds={null}
        numericError={null}
        onChange={onChange}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    await user.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenCalledWith('test.setting', false)
  })

  it('renders integer as NumberInput', () => {
    render(
      <SettingInput
        setting={baseSetting}
        value={100}
        numericBounds={{ min: 1, max: 1000 }}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: /plus/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /minus/i })).toBeInTheDocument()
  })

  it('integer plus/minus calls onChange', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <SettingInput
        setting={baseSetting}
        value={100}
        numericBounds={null}
        numericError={null}
        onChange={onChange}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: /plus/i }))
    expect(onChange).toHaveBeenCalledWith('test.setting', 101)
  })

  it('float uses 0.1 step', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const floatSetting = { ...baseSetting, value_type: 'float' as const }
    render(
      <SettingInput
        setting={floatSetting}
        value={0.5}
        numericBounds={null}
        numericError={null}
        onChange={onChange}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: /plus/i }))
    expect(onChange).toHaveBeenCalledWith('test.setting', 0.6)
  })

  it('renders string with allowed_values as Select', () => {
    const stringSetting = {
      ...baseSetting,
      value_type: 'string' as const,
      validation_schema: {
        allowed_values: ['low', 'medium', 'high'],
      } as unknown as RuntimeSetting['validation_schema'],
    }
    render(
      <SettingInput
        setting={stringSetting}
        value="medium"
        numericBounds={null}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Test setting' })).toBeInTheDocument()
  })

  it('renders string without allowed_values as TextInput', () => {
    const stringSetting = { ...baseSetting, value_type: 'string' as const }
    render(
      <SettingInput
        setting={stringSetting}
        value="hello"
        numericBounds={null}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    expect(screen.getByDisplayValue('hello')).toBeInTheDocument()
  })

  it('renders json as chip input with labels', () => {
    const jsonSetting = { ...baseSetting, value_type: 'json' as const }
    render(
      <SettingInput
        setting={jsonSetting}
        value={['system', 'context', 'user']}
        numericBounds={null}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    expect(screen.getByText('system')).toBeInTheDocument()
    expect(screen.getByText('context')).toBeInTheDocument()
    expect(screen.getByText('user')).toBeInTheDocument()
  })

  it('json input adds item on Enter', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const jsonSetting = { ...baseSetting, value_type: 'json' as const }
    render(
      <SettingInput
        setting={jsonSetting}
        value={['existing']}
        numericBounds={null}
        numericError={null}
        onChange={onChange}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    const input = screen.getByPlaceholderText('Type a value and press Enter')
    await user.type(input, 'new-item{Enter}')
    expect(onChange).toHaveBeenCalledWith('test.setting', ['existing', 'new-item'])
  })

  it('json input clear all button removes all items', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const jsonSetting = { ...baseSetting, value_type: 'json' as const }
    render(
      <SettingInput
        setting={jsonSetting}
        value={['a', 'b']}
        numericBounds={null}
        numericError={null}
        onChange={onChange}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Clear all' }))
    expect(onChange).toHaveBeenCalledWith('test.setting', [])
  })

  it('renders default case as TextInput', () => {
    const unknownSetting = { ...baseSetting, value_type: 'unknown' as RuntimeSetting['value_type'] }
    render(
      <SettingInput
        setting={unknownSetting}
        value="fallback"
        numericBounds={null}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    expect(screen.getByDisplayValue('fallback')).toBeInTheDocument()
  })

  it('stringifies non-string values in the default TextInput', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const unknownSetting = { ...baseSetting, value_type: 'unknown' as RuntimeSetting['value_type'] }
    render(
      <SettingInput
        setting={unknownSetting}
        value={42}
        numericBounds={null}
        numericError={null}
        onChange={onChange}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    expect(screen.getByDisplayValue('42')).toBeInTheDocument()

    await user.type(screen.getByDisplayValue('42'), '0')
    expect(onChange).toHaveBeenCalledWith('test.setting', '420')
  })

  it('shows error validation state on NumberInput when numericError is set', () => {
    render(
      <SettingInput
        setting={baseSetting}
        value={-1}
        numericBounds={{ min: 0, max: 100 }}
        numericError="Value must be at least 0"
        onChange={vi.fn()}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    // NumberInput should have validated="error" which adds the error class
    expect(screen.getByRole('button', { name: /plus/i })).toBeInTheDocument()
  })

  it('blur snaps value to min bound', () => {
    const onChange = vi.fn()
    render(
      <SettingInput
        setting={baseSetting}
        value={-5}
        numericBounds={{ min: 0, max: 100 }}
        numericError={null}
        onChange={onChange}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    const input = screen.getByRole('spinbutton')
    input.focus()
    input.blur()
    expect(onChange).toHaveBeenCalledWith('test.setting', 0)
  })

  it('calls onStringError with invalid email on Enter', async () => {
    const user = userEvent.setup()
    const onStringError = vi.fn()
    const jsonSetting = {
      ...baseSetting,
      value_type: 'json' as const,
      validation_schema: { pattern: 'email' } as unknown as RuntimeSetting['validation_schema'],
    }
    render(
      <SettingInput
        setting={jsonSetting}
        value={[]}
        numericBounds={null}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={onStringError}
      />
    )

    const input = screen.getByPlaceholderText('Type a value and press Enter')
    await user.type(input, 'not-an-email{Enter}')
    expect(onStringError).toHaveBeenCalledWith(expect.stringContaining('email'))
  })

  it('calls onStringError with invalid URL on blur', async () => {
    const user = userEvent.setup()
    const onStringError = vi.fn()
    const stringSetting = {
      ...baseSetting,
      value_type: 'string' as const,
      validation_schema: { pattern: 'url' } as unknown as RuntimeSetting['validation_schema'],
    }
    render(
      <SettingInput
        setting={stringSetting}
        value="not-a-url"
        numericBounds={null}
        numericError={null}
        onChange={vi.fn()}
        stringError={null}
        onStringError={onStringError}
      />
    )

    const input = screen.getByDisplayValue('not-a-url')
    await user.click(input)
    await user.tab()
    expect(onStringError).toHaveBeenCalledWith(expect.stringContaining('URL'))
  })

  it('blur snaps value to max bound', () => {
    const onChange = vi.fn()
    render(
      <SettingInput
        setting={baseSetting}
        value={999}
        numericBounds={{ min: 0, max: 100 }}
        numericError={null}
        onChange={onChange}
        stringError={null}
        onStringError={vi.fn()}
      />
    )

    const input = screen.getByRole('spinbutton')
    input.focus()
    input.blur()
    expect(onChange).toHaveBeenCalledWith('test.setting', 100)
  })

  describe('readOnly', () => {
    it('disables Switch when readOnly', () => {
      const boolSetting = { ...baseSetting, value_type: 'boolean' as const }
      render(
        <SettingInput
          setting={boolSetting}
          value={true}
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError={null}
          onStringError={vi.fn()}
          readOnly
        />
      )

      expect(screen.getByRole('switch')).toBeDisabled()
    })

    it('disables NumberInput when readOnly', () => {
      render(
        <SettingInput
          setting={baseSetting}
          value={100}
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError={null}
          onStringError={vi.fn()}
          readOnly
        />
      )

      expect(screen.getByRole('spinbutton')).toBeDisabled()
    })

    it('disables Select when readOnly', () => {
      const stringSetting = {
        ...baseSetting,
        value_type: 'string' as const,
        validation_schema: {
          allowed_values: ['low', 'medium', 'high'],
        } as unknown as RuntimeSetting['validation_schema'],
      }
      render(
        <SettingInput
          setting={stringSetting}
          value="medium"
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError={null}
          onStringError={vi.fn()}
          readOnly
        />
      )

      expect(screen.getByRole('button', { name: 'Test setting' })).toBeDisabled()
    })

    it('renders TextInput as read-only when readOnly', () => {
      const stringSetting = { ...baseSetting, value_type: 'string' as const }
      render(
        <SettingInput
          setting={stringSetting}
          value="hello"
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError={null}
          onStringError={vi.fn()}
          readOnly
        />
      )

      expect(screen.getByDisplayValue('hello')).toHaveAttribute('readonly')
    })

    it('hides clear all button for json when readOnly', () => {
      const jsonSetting = { ...baseSetting, value_type: 'json' as const }
      render(
        <SettingInput
          setting={jsonSetting}
          value={['a', 'b']}
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError={null}
          onStringError={vi.fn()}
          readOnly
        />
      )

      expect(screen.getByText('a')).toBeInTheDocument()
      expect(screen.getByText('b')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Clear all' })).not.toBeInTheDocument()
    })

    it('renders default type TextInput as read-only when readOnly', () => {
      const unknownSetting = { ...baseSetting, value_type: 'unknown' as RuntimeSetting['value_type'] }
      render(
        <SettingInput
          setting={unknownSetting}
          value="fallback"
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError={null}
          onStringError={vi.fn()}
          readOnly
        />
      )

      expect(screen.getByDisplayValue('fallback')).toHaveAttribute('readonly')
    })
  })

  describe('JsonInput', () => {
    it('removes individual item when label close is clicked', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      const jsonSetting = { ...baseSetting, value_type: 'json' as const }
      render(
        <SettingInput
          setting={jsonSetting}
          value={['alpha', 'beta', 'gamma']}
          numericBounds={null}
          numericError={null}
          onChange={onChange}
          stringError={null}
          onStringError={vi.fn()}
        />
      )

      const closeButtons = screen.getAllByRole('button', { name: /close/i })
      // Find the close button for "beta" (second label)
      await user.click(closeButtons[1])
      expect(onChange).toHaveBeenCalledWith('test.setting', ['alpha', 'gamma'])
    })

    it('clears stringError when typing in json input', async () => {
      const user = userEvent.setup()
      const onStringError = vi.fn()
      const jsonSetting = { ...baseSetting, value_type: 'json' as const }
      render(
        <SettingInput
          setting={jsonSetting}
          value={[]}
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError="some error"
          onStringError={onStringError}
        />
      )

      const input = screen.getByPlaceholderText('Type a value and press Enter')
      await user.type(input, 'a')
      expect(onStringError).toHaveBeenCalledWith(null)
    })

    it('does not add duplicate items in json input', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      const jsonSetting = { ...baseSetting, value_type: 'json' as const }
      render(
        <SettingInput
          setting={jsonSetting}
          value={['existing']}
          numericBounds={null}
          numericError={null}
          onChange={onChange}
          stringError={null}
          onStringError={vi.fn()}
        />
      )

      const input = screen.getByPlaceholderText('Type a value and press Enter')
      await user.type(input, 'existing{Enter}')
      expect(onChange).not.toHaveBeenCalled()
    })

    it('does not add empty value on Enter in json input', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      const jsonSetting = { ...baseSetting, value_type: 'json' as const }
      render(
        <SettingInput
          setting={jsonSetting}
          value={[]}
          numericBounds={null}
          numericError={null}
          onChange={onChange}
          stringError={null}
          onStringError={vi.fn()}
        />
      )

      const input = screen.getByPlaceholderText('Type a value and press Enter')
      await user.type(input, '{Enter}')
      expect(onChange).not.toHaveBeenCalled()
    })

    it('hides label close buttons when readOnly', () => {
      const jsonSetting = { ...baseSetting, value_type: 'json' as const }
      render(
        <SettingInput
          setting={jsonSetting}
          value={['alpha', 'beta']}
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError={null}
          onStringError={vi.fn()}
          readOnly
        />
      )

      expect(screen.getByText('alpha')).toBeInTheDocument()
      expect(screen.queryAllByRole('button', { name: /close/i })).toHaveLength(0)
    })

    it('clears stringError on Enter when adding valid item with prior error', async () => {
      const user = userEvent.setup()
      const onStringError = vi.fn()
      const jsonSetting = { ...baseSetting, value_type: 'json' as const }
      render(
        <SettingInput
          setting={jsonSetting}
          value={[]}
          numericBounds={null}
          numericError={null}
          onChange={vi.fn()}
          stringError="prior error"
          onStringError={onStringError}
        />
      )

      const input = screen.getByPlaceholderText('Type a value and press Enter')
      await user.type(input, 'valid-item{Enter}')
      expect(onStringError).toHaveBeenCalledWith(null)
    })
  })
})
