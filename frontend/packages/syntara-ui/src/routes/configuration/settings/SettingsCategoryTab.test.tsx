import type { SettingsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SettingsCategoryTab } from './SettingsCategoryTab'

type RuntimeSetting = SettingsAPI.components['schemas']['RuntimeSettingRead']

const makeSetting = (overrides: Partial<RuntimeSetting> = {}): RuntimeSetting => ({
  id: '1',
  key: 'context_manager.max_total_tokens',
  name: 'Max total tokens',
  description: 'Maximum total tokens',
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
  validation_schema: null,
  version: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...overrides,
})

const defaultProps = {
  edits: new Map<string, unknown>(),
  onChange: vi.fn(),
  onResetField: vi.fn(),
}

describe('SettingsCategoryTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('has no accessibility violations', async () => {
    const settings = [makeSetting()]
    const { container } = render(<SettingsCategoryTab settings={settings} {...defaultProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('reset to defaults button is disabled when all values are at defaults', () => {
    const settings = [
      makeSetting({ key: 'a', default_value: 100, effective_value: 100, value: null }),
      makeSetting({ key: 'b', default_value: 200, effective_value: 200, value: null }),
    ]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    expect(screen.getByRole('button', { name: 'Reset to defaults' })).toBeDisabled()
  })

  it('reset to defaults button is enabled when a setting has a saved non-default value', () => {
    const settings = [
      makeSetting({ key: 'a', default_value: 100, effective_value: 500, value: 500 }),
      makeSetting({ key: 'b', default_value: 200, effective_value: 200, value: null }),
    ]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    expect(screen.getByRole('button', { name: 'Reset to defaults' })).toBeEnabled()
  })

  it('reset to defaults button is enabled when there are local edits', () => {
    const settings = [makeSetting({ key: 'a', default_value: 100, effective_value: 100, value: null })]
    const edits = new Map<string, unknown>([['a', 999]])
    render(<SettingsCategoryTab settings={settings} {...defaultProps} edits={edits} />)

    expect(screen.getByRole('button', { name: 'Reset to defaults' })).toBeEnabled()
  })

  it('reset all sets all values to defaults locally via onChange', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const settings = [
      makeSetting({ key: 'a', default_value: 100, effective_value: 500, value: 500 }),
      makeSetting({ key: 'b', default_value: 200, effective_value: 300, value: 300 }),
    ]

    render(<SettingsCategoryTab settings={settings} {...defaultProps} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    await user.click(screen.getByRole('button', { name: 'Reset all settings' }))

    expect(onChange).toHaveBeenCalledWith('a', 100)
    expect(onChange).toHaveBeenCalledWith('b', 200)
  })

  it('modal closes on cancel without resetting values', async () => {
    const user = userEvent.setup()
    const settings = [makeSetting({ key: 'a', default_value: 100, effective_value: 500, value: 500 })]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    expect(screen.getByText(/will not take effect until you click Save/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByText(/will not take effect until you click Save/)).not.toBeInTheDocument()
  })

  it('kebab reset calls onResetField', async () => {
    const user = userEvent.setup()
    const onResetField = vi.fn()
    const settings = [makeSetting({ key: 'a', default_value: 100, effective_value: 500, value: 500 })]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} onResetField={onResetField} />)

    await user.click(screen.getByLabelText('Actions for Max total tokens'))
    await user.click(screen.getByRole('menuitem', { name: 'Reset to default' }))

    expect(onResetField).toHaveBeenCalledWith('a')
  })

  it('renders group sections', () => {
    const settings = [makeSetting({ key: 'a', group: 'Token limits' }), makeSetting({ key: 'b', group: 'Performance' })]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    expect(screen.getByRole('group', { name: 'Token limits' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Performance' })).toBeInTheDocument()
  })

  it('calls onChange when a field value changes', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const settings = [makeSetting({ key: 'a', default_value: 100, effective_value: 100 })]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: /plus/i }))

    expect(onChange).toHaveBeenCalledWith('a', 101)
  })

  it('hides reset to defaults button when readOnly', () => {
    const settings = [makeSetting({ key: 'a', default_value: 100, effective_value: 500, value: 500 })]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} readOnly />)

    expect(screen.queryByRole('button', { name: 'Reset to defaults' })).not.toBeInTheDocument()
  })

  it('hides kebab menu when readOnly', () => {
    const settings = [makeSetting({ key: 'a', default_value: 100, effective_value: 500, value: 500 })]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} readOnly />)

    expect(screen.queryByLabelText('Actions for Max total tokens')).not.toBeInTheDocument()
  })

  it('hides setting when depends_on target is false', () => {
    const settings = [
      makeSetting({
        key: 'ctx.toggle',
        name: 'Toggle',
        group: 'G',
        value_type: 'boolean',
        default_value: false,
        effective_value: false,
      }),
      makeSetting({
        key: 'ctx.child',
        name: 'Child',
        group: 'G',
        value_type: 'integer',
        default_value: 10,
        effective_value: 10,
        depends_on: 'ctx.toggle',
      }),
    ]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    expect(screen.getByText('Toggle')).toBeInTheDocument()
    expect(screen.queryByText('Child')).not.toBeInTheDocument()
  })

  it('shows setting when depends_on target is true', () => {
    const settings = [
      makeSetting({
        key: 'ctx.toggle',
        name: 'Toggle',
        group: 'G',
        value_type: 'boolean',
        default_value: true,
        effective_value: true,
      }),
      makeSetting({
        key: 'ctx.child',
        name: 'Child',
        group: 'G',
        value_type: 'integer',
        default_value: 10,
        effective_value: 10,
        depends_on: 'ctx.toggle',
      }),
    ]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    expect(screen.getByText('Toggle')).toBeInTheDocument()
    expect(screen.getByText('Child')).toBeInTheDocument()
  })

  it('always shows settings without depends_on even when booleans are false', () => {
    const settings = [
      makeSetting({
        key: 'ctx.toggle',
        name: 'Toggle',
        group: 'G',
        value_type: 'boolean',
        default_value: false,
        effective_value: false,
      }),
      makeSetting({
        key: 'ctx.independent',
        name: 'Independent',
        group: 'G',
        value_type: 'integer',
        default_value: 5,
        effective_value: 5,
        depends_on: null,
      }),
    ]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    expect(screen.getByText('Independent')).toBeInTheDocument()
  })

  it('hides setting when depends_on targets a boolean in a different group', () => {
    const settings = [
      makeSetting({
        key: 'ctx.toggle',
        name: 'Toggle',
        group: 'Group A',
        value_type: 'boolean',
        default_value: false,
        effective_value: false,
      }),
      makeSetting({
        key: 'ctx.child',
        name: 'Child',
        group: 'Group B',
        value_type: 'integer',
        default_value: 10,
        effective_value: 10,
        depends_on: 'ctx.toggle',
      }),
    ]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    expect(screen.getByText('Toggle')).toBeInTheDocument()
    expect(screen.queryByText('Child')).not.toBeInTheDocument()
  })

  it('shows setting when depends_on references a nonexistent key', () => {
    const settings = [
      makeSetting({
        key: 'ctx.child',
        name: 'Orphan',
        group: 'G',
        value_type: 'integer',
        default_value: 10,
        effective_value: 10,
        depends_on: 'ctx.nonexistent',
      }),
    ]
    render(<SettingsCategoryTab settings={settings} {...defaultProps} />)

    expect(screen.getByText('Orphan')).toBeInTheDocument()
  })

  it('local edit toggling parent shows/hides dependent settings', () => {
    const settings = [
      makeSetting({
        key: 'ctx.toggle',
        name: 'Toggle',
        group: 'G',
        value_type: 'boolean',
        default_value: true,
        effective_value: true,
      }),
      makeSetting({
        key: 'ctx.child',
        name: 'Child',
        group: 'G',
        value_type: 'integer',
        default_value: 10,
        effective_value: 10,
        depends_on: 'ctx.toggle',
      }),
    ]

    const edits = new Map<string, unknown>([['ctx.toggle', false]])
    render(<SettingsCategoryTab settings={settings} {...defaultProps} edits={edits} />)

    expect(screen.queryByText('Child')).not.toBeInTheDocument()
  })
})
