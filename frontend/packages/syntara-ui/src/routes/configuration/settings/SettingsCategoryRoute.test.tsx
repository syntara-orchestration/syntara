import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SettingsCategoryRoute } from './SettingsCategoryRoute'
import { SettingsCategoryTabContext } from './SettingsCategoryTabContext'

const mockUseParams = vi.hoisted(() => vi.fn())

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return { ...actual, useParams: mockUseParams }
})

const applicationSettings = [
  {
    id: 'application.debug_mode',
    key: 'application.debug_mode',
    name: 'Debug mode',
    description: 'Enable debug logging',
    helper_text: null,
    depends_on: null,
    category: 'application',
    group: 'General',
    value: null,
    default_value: false,
    effective_value: false,
    value_type: 'boolean' as const,
    requires_restart: false,
    cache_ttl_seconds: null,
    validation_schema: null,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

function setCategory(category?: string) {
  mockUseParams.mockReturnValue({ category })
}

function renderCategoryRoute(category: string | undefined) {
  setCategory(category)

  return render(
    <SettingsCategoryTabContext
      value={{
        settingsByCategory: new Map([['application', applicationSettings]]),
        edits: new Map(),
        onChange: () => undefined,
        onResetField: () => undefined,
        onValidationChange: () => undefined,
        readOnly: false,
      }}
    >
      <SettingsCategoryRoute />
    </SettingsCategoryTabContext>
  )
}

describe('SettingsCategoryRoute', () => {
  beforeEach(() => {
    setCategory('application')
  })

  it('renders the category selected by the route parameter', () => {
    renderCategoryRoute('application')

    expect(screen.getByText('Debug mode')).toBeInTheDocument()
  })

  it('renders nothing when the route has no category parameter', () => {
    const { container } = renderCategoryRoute(undefined)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the category tab context is missing', () => {
    const { container } = render(<SettingsCategoryRoute />)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders an empty category when the route category has no settings', () => {
    renderCategoryRoute('unknown')

    expect(screen.queryByText('Debug mode')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset to defaults' })).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderCategoryRoute('application')

    expect(await axe(container)).toHaveNoViolations()
  })
})
