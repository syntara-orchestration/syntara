import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SettingsCategoryRoute } from './SettingsCategoryRoute'
import { SettingsCategoryTabContext } from './SettingsCategoryTabContext'

const mockUseRouterState = vi.hoisted(() => vi.fn())

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return { ...actual, useRouterState: mockUseRouterState }
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

function setPathname(pathname: string) {
  mockUseRouterState.mockImplementation((options: { select: (state: { location: { pathname: string } }) => unknown }) =>
    options.select({ location: { pathname } })
  )
}

function renderCategoryRoute(pathname = '/system-administration/settings/application') {
  setPathname(pathname)

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
    setPathname('/system-administration/settings/application')
  })

  it('renders the category selected by the route parameter', () => {
    renderCategoryRoute()

    expect(screen.getByText('Debug mode')).toBeInTheDocument()
  })

  it('renders nothing when the path is outside the settings route', () => {
    const { container } = renderCategoryRoute('/system-administration/users')

    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the settings path has no category', () => {
    const { container } = renderCategoryRoute('/system-administration/settings/')

    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the category tab context is missing', () => {
    const { container } = render(<SettingsCategoryRoute />)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders an empty category when the route category has no settings', () => {
    renderCategoryRoute('/system-administration/settings/unknown')

    expect(screen.queryByText('Debug mode')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset to defaults' })).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderCategoryRoute()

    expect(await axe(container)).toHaveNoViolations()
  })
})
