import type { SettingsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SettingField } from './SettingField'

type RuntimeSetting = SettingsAPI.components['schemas']['RuntimeSettingRead']

// Cast validation_schema since the generated type is Record<string, never>
// but our API actually returns objects with min/max/allowed_values keys.
const baseSetting: RuntimeSetting = {
  id: '123',
  key: 'context_manager.max_total_tokens',
  name: 'Max total tokens',
  description: 'Maximum total tokens in context package',
  helper_text: 'Minimum 1 token',
  depends_on: null,
  category: 'context_manager',
  group: 'Token limits',
  value: null,
  default_value: 4000,
  effective_value: 4000,
  value_type: 'integer',
  requires_restart: false,
  cache_ttl_seconds: null,
  validation_schema: { min: 1 },
  version: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('SettingField', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(
      <SettingField setting={baseSetting} value={4000} onChange={vi.fn()} onResetSingle={vi.fn()} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders integer setting with NumberInput', () => {
    render(<SettingField setting={baseSetting} value={4000} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.getByText('Max total tokens')).toBeInTheDocument()
    // Description appears in popover, not helper text (non-notifications category)
    expect(screen.getByLabelText(/Help for Max total tokens/)).toBeInTheDocument()
  })

  it('renders boolean setting with Switch', () => {
    const boolSetting = {
      ...baseSetting,
      key: 'context_manager.enable_hybrid_search',
      name: 'Enable hybrid search',
      value_type: 'boolean' as const,
      validation_schema: null,
    }
    render(<SettingField setting={boolSetting} value={true} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.getByText('Enable hybrid search')).toBeInTheDocument()
  })

  it('renders string setting with allowed_values as FormSelect', () => {
    const stringSetting = {
      ...baseSetting,
      key: 'context_manager.compression_mode',
      name: 'Compression mode',
      value_type: 'string' as const,
      validation_schema: {
        allowed_values: ['extractive', 'abstractive'],
      } as unknown as RuntimeSetting['validation_schema'],
    }
    render(<SettingField setting={stringSetting} value="extractive" onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.getByText('Compression mode')).toBeInTheDocument()
  })

  it('shows helper_text from API', () => {
    render(<SettingField setting={baseSetting} value={4000} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.getByText('Minimum 1 token')).toBeInTheDocument()
  })

  it('renders boolean setting with description in popover', () => {
    const boolSetting = {
      ...baseSetting,
      key: 'context_manager.enable_hybrid_search',
      name: 'Hybrid search',
      description: 'Enable hybrid search (semantic + lexical)',
      value_type: 'boolean' as const,
      value: true,
      validation_schema: null,
    }
    render(<SettingField setting={boolSetting} value={true} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.getByText('Hybrid search')).toBeInTheDocument()
    expect(screen.getByLabelText(/Help for Hybrid search/)).toBeInTheDocument()
    expect(screen.getByText('Enabled')).toBeInTheDocument()
  })

  it('renders notification setting with helper_text, no popover', () => {
    const notifSetting = {
      ...baseSetting,
      key: 'notifications.email_enabled',
      name: 'Email notifications',
      description: 'Send email notifications for workflow events',
      helper_text: 'Requires SMTP configuration',
      category: 'notifications',
      value_type: 'boolean' as const,
      validation_schema: null,
    }
    render(<SettingField setting={notifSetting} value={true} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.getByText('Email notifications')).toBeInTheDocument()
    expect(screen.getByText('Requires SMTP configuration')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Help for/)).not.toBeInTheDocument()
  })

  it('renders string setting without allowed_values as TextInput', () => {
    const stringSetting = {
      ...baseSetting,
      key: 'context_manager.some_string',
      name: 'Some string',
      value_type: 'string' as const,
      validation_schema: null,
    }
    render(<SettingField setting={stringSetting} value="hello" onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.getByText('Some string')).toBeInTheDocument()
    expect(screen.getByDisplayValue('hello')).toBeInTheDocument()
  })

  it('renders json setting as comma-separated TextInput', () => {
    const jsonSetting = {
      ...baseSetting,
      key: 'context_manager.priority_order',
      name: 'Priority order',
      value_type: 'json' as const,
      validation_schema: null,
    }
    render(
      <SettingField
        setting={jsonSetting}
        value={['system', 'context', 'user']}
        onChange={vi.fn()}
        onResetSingle={vi.fn()}
      />
    )

    expect(screen.getByText('Priority order')).toBeInTheDocument()
    expect(screen.getByText('system')).toBeInTheDocument()
    expect(screen.getByText('context')).toBeInTheDocument()
    expect(screen.getByText('user')).toBeInTheDocument()
  })

  it('renders float setting with helper_text', () => {
    const floatSetting = {
      ...baseSetting,
      key: 'context_manager.compression_temperature',
      name: 'Compression temperature',
      helper_text: 'Range 0.0-1.0. Lower is more deterministic.',
      value_type: 'float' as const,
      validation_schema: { min: 0, max: 1 } as unknown as RuntimeSetting['validation_schema'],
    }
    render(<SettingField setting={floatSetting} value={0.3} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.getByText('Compression temperature')).toBeInTheDocument()
    expect(screen.getByText('Range 0.0-1.0. Lower is more deterministic.')).toBeInTheDocument()
  })

  it('shows no helper text when helper_text is null', () => {
    const setting = {
      ...baseSetting,
      helper_text: null,
      validation_schema: { max: 100 } as unknown as RuntimeSetting['validation_schema'],
    }
    render(<SettingField setting={setting} value={50} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    expect(screen.queryByText(/max: 100/)).not.toBeInTheDocument()
  })

  it('calls onChange when integer plus button clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SettingField setting={baseSetting} value={4000} onChange={onChange} onResetSingle={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /plus/i }))
    expect(onChange).toHaveBeenCalledWith('context_manager.max_total_tokens', 4001)
  })

  it('calls onChange when boolean toggled', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const boolSetting = {
      ...baseSetting,
      key: 'context_manager.enable_hybrid_search',
      name: 'Enable hybrid search',
      value_type: 'boolean' as const,
      validation_schema: null,
    }
    render(<SettingField setting={boolSetting} value={true} onChange={onChange} onResetSingle={vi.fn()} />)

    await user.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenCalledWith('context_manager.enable_hybrid_search', false)
  })

  it('shows kebab menu with reset to default option', async () => {
    const user = userEvent.setup()
    render(<SettingField setting={baseSetting} value={4000} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    const kebab = screen.getByLabelText('Actions for Max total tokens')
    expect(kebab).toBeInTheDocument()

    await user.click(kebab)
    expect(screen.getByRole('menuitem', { name: 'Reset to default' })).toBeInTheDocument()
  })

  it('kebab reset is disabled when value equals default', async () => {
    const user = userEvent.setup()
    render(<SettingField setting={baseSetting} value={4000} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    await user.click(screen.getByLabelText('Actions for Max total tokens'))
    const resetItem = screen.getByRole('menuitem', { name: 'Reset to default' })
    expect(resetItem).toHaveAttribute('disabled')
  })

  it('kebab reset is enabled when value differs from default', async () => {
    const user = userEvent.setup()
    render(<SettingField setting={baseSetting} value={8000} onChange={vi.fn()} onResetSingle={vi.fn()} />)

    await user.click(screen.getByLabelText('Actions for Max total tokens'))
    const resetItem = screen.getByRole('menuitem', { name: 'Reset to default' })
    expect(resetItem).not.toHaveAttribute('disabled')
  })

  it('kebab reset calls onResetSingle with key', async () => {
    const user = userEvent.setup()
    const onResetSingle = vi.fn()
    render(<SettingField setting={baseSetting} value={8000} onChange={vi.fn()} onResetSingle={onResetSingle} />)

    await user.click(screen.getByLabelText('Actions for Max total tokens'))
    await user.click(screen.getByRole('menuitem', { name: 'Reset to default' }))
    expect(onResetSingle).toHaveBeenCalledWith('context_manager.max_total_tokens')
  })

  it('hides kebab menu when readOnly', () => {
    render(<SettingField setting={baseSetting} value={4000} onChange={vi.fn()} onResetSingle={vi.fn()} readOnly />)

    expect(screen.queryByLabelText('Actions for Max total tokens')).not.toBeInTheDocument()
  })
})
