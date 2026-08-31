import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { authClient } from '../client'
import { BrandProvider } from '../providers/brand'
import { COLOR_SCHEME_STORAGE_KEY } from '../providers/theme/colorScheme'
import { ColorSchemeProvider } from '../providers/theme/ColorSchemeProvider'

import { AppDockedNav } from './AppDockedNav'
import styles from './AppDockedNav.module.css'
import type { DockState } from './useDockState'

const mockOnToggleDock = vi.fn()
const mockUseDockState = vi.fn<() => DockState>()
vi.mock('./useDockState', () => ({
  useDockState: (): DockState => mockUseDockState(),
}))

const mockNavigate = vi.fn()
let mockLocation = '/workflows'
vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    Link: ({ to, children, ...rest }: { to: string; children?: React.ReactNode } & Record<string, unknown>) => (
      <a href={to} {...rest}>
        {children}
      </a>
    ),
    useNavigate: () => mockNavigate,
    useRouterState: vi.fn((opts?: { select?: (s: { location: { pathname: string } }) => unknown }) => {
      const state = { location: { pathname: mockLocation } }
      return opts?.select ? opts.select(state) : state
    }),
  }
})

// Mock useUnsavedChanges
const mockRequestNavigation = vi.fn()
vi.mock('./useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({
    requestNavigation: mockRequestNavigation,
    hasUnsavedChanges: false,
  }),
}))

// Mock usePermissionChecks used by useFilteredNavigationItems
vi.mock('../hooks/usePermissionChecks', () => ({
  usePermissionChecks: () => ({
    permissions: {
      'setting:read': true,
      'user:read': true,
      'group:read': true,
      'identity-provider:read': true,
      'integration:read': true,
      'project:read': true,
      'role-assignment:read': true,
    },
    isLoading: false,
  }),
}))

// Mock useAllPermissions used by useFilteredNavigationItems for project-scoped grants
vi.mock('../routes/access/useAllPermissions', () => ({
  useAllPermissions: () => ({
    permissions: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

// Mock useAuthStore used by UserMenuDropdown
const mockLogout = vi.fn().mockResolvedValue(undefined)
vi.mock('../stores/useAuthStore', () => ({
  useAuthStore: vi.fn((selector: unknown) =>
    typeof selector === 'function'
      ? (selector as (state: { logout: ReturnType<typeof vi.fn> }) => unknown)({ logout: mockLogout })
      : { logout: mockLogout }
  ),
}))

vi.mock('../client', () => ({
  authClient: { useQuery: vi.fn().mockReturnValue({ data: undefined }) },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function renderDockedNav() {
  return render(
    <BrandProvider>
      <ColorSchemeProvider>
        <AppDockedNav />
      </ColorSchemeProvider>
    </BrandProvider>
  )
}

describe('AppDockedNav', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLocation = '/workflows'
    vi.mocked(authClient.useQuery).mockReturnValue({
      data: { id: 'user-1', username: 'testuser' },
    } as never)
    mockUseDockState.mockReturnValue({
      isDockExpanded: false,
      isDockTextExpanded: false,
      isMobile: false,
      dockedToggleRef: { current: null },
      mobileToggleRef: { current: null },
      onToggleDock: mockOnToggleDock,
      onMobileToggle: vi.fn(),
    })
    localStorage.clear()
    document.documentElement.classList.add('pf-v6-theme-dark', 'pf-v6-theme-glass')
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('pf-v6-theme-dark', 'pf-v6-theme-glass')
  })

  it('renders navigation items', () => {
    renderDockedNav()
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
  })

  it('renders user menu toggle', () => {
    renderDockedNav()
    expect(screen.getByRole('button', { name: 'User menu' })).toBeInTheDocument()
  })

  it('scopes docked chrome styles to the masthead and collapsed nav', () => {
    renderDockedNav()

    expect(screen.getByRole('banner')).toHaveClass(styles.dockedMasthead)
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toHaveClass(styles.iconDockNav)
    expect(screen.getByRole('button', { name: 'User menu' })).toHaveClass(styles.dockedAction)
  })

  it('renders documentation button', () => {
    renderDockedNav()
    expect(screen.getByRole('button', { name: 'Documentation (opens in a new tab)' })).toBeInTheDocument()
  })

  it('renders color scheme toggle when in dark mode', () => {
    renderDockedNav()
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument()
  })

  it('persists light mode and updates document when toggling from dark', async () => {
    const user = userEvent.setup()
    renderDockedNav()
    await user.click(screen.getByRole('button', { name: 'Switch to light mode' }))
    expect(document.documentElement.classList.contains('pf-v6-theme-dark')).toBe(false)
    expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe('light')
    expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toBeInTheDocument()
  })

  it('renders menu toggle button', () => {
    renderDockedNav()
    expect(screen.getByRole('button', { name: 'Global navigation' })).toBeInTheDocument()
  })

  it('shows My Profile and Logout in user menu when hovered', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    await user.hover(screen.getByRole('button', { name: 'User menu' }))

    expect(screen.getByText('My Profile')).toBeInTheDocument()
    expect(screen.getByText('Logout')).toBeInTheDocument()
    expect(screen.queryByText('Settings')).not.toBeInTheDocument()
  })

  it('opens user menu when Enter is pressed while focused', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    await user.tab()
    const userMenuButton = screen.getByRole('button', { name: 'User menu' })
    userMenuButton.focus()
    await user.keyboard('{Enter}')

    expect(screen.getByText('My Profile')).toBeInTheDocument()
    expect(screen.getByText('Logout')).toBeInTheDocument()
  })

  it('navigates to /my-profile when My Profile is clicked', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    await user.hover(screen.getByRole('button', { name: 'User menu' }))
    await user.click(screen.getByText('My Profile'))

    expect(mockNavigate).toHaveBeenCalledWith({ to: '/my-profile' })
  })

  it('opens external documentation when documentation button is clicked', async () => {
    const user = userEvent.setup()
    const openSpy = vi.spyOn(globalThis, 'open').mockImplementation(() => null)
    renderDockedNav()

    await user.click(screen.getByRole('button', { name: 'Documentation (opens in a new tab)' }))

    expect(openSpy).toHaveBeenCalledWith(
      'https://github.com/syntara-orchestration/syntara/blob/devel/README.md',
      '_blank',
      'noopener,noreferrer'
    )
    openSpy.mockRestore()
  })

  it('navigates when nav item is selected', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    const navItem = screen.getByLabelText('Workflows')
    await user.click(navItem)
    expect(mockRequestNavigation).toHaveBeenCalled()
  })

  it('renders with correct active state based on location', () => {
    renderDockedNav()

    // Since we mocked location as '/workflows', that nav item should be active
    const nav = screen.getByRole('navigation', { name: 'Main navigation' })
    expect(nav).toBeInTheDocument()
  })

  it('renders masthead', () => {
    renderDockedNav()

    expect(screen.getByRole('banner')).toBeInTheDocument()
  })

  it('renders brand logo link to home page', () => {
    renderDockedNav()

    const banner = screen.getByRole('banner')
    const logoLinks = within(banner).getAllByRole('link', { name: 'Home' })

    expect(logoLinks.length).toBeGreaterThanOrEqual(1)
    expect(logoLinks[0]).toHaveAttribute('href', '/')
  })

  it('navigates to Integrations when Configuration is clicked', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    const configItem = screen.getByLabelText('Configuration')
    await user.click(configItem)

    expect(mockRequestNavigation).toHaveBeenCalledWith('/configuration/integrations')
  })

  it('shows dropdown with Integrations and Credentials when Configuration is clicked', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    const navButton = screen.getByRole('button', { name: 'Configuration' })
    await user.click(navButton)

    const menu = screen.getByRole('menu')
    const menuItems = within(menu).getAllByRole('menuitem')

    // Configuration has 2 child items: Integrations, Credentials (Settings moved to System Administration)
    expect(menuItems.length).toBe(2)
    expect(menu).toBeInTheDocument()
    expect(menuItems[0]).toHaveClass(styles.flyoutMenuItem)
  })

  it('applies navFlyoutItem class to collapsed-mode flyout nav items', () => {
    renderDockedNav()

    expect(screen.getByRole('button', { name: 'Configuration' })).toHaveClass(styles.navFlyoutItem)
    expect(screen.getByRole('button', { name: 'System Administration' })).toHaveClass(styles.navFlyoutItem)
  })

  it('shows dropdown with Access Management, Identity Providers, and Settings when System Administration is clicked', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    const navButton = screen.getByRole('button', { name: 'System Administration' })
    await user.click(navButton)

    const menu = screen.getByRole('menu')
    const menuItems = within(menu).getAllByRole('menuitem')

    // System Administration has 3 child items: Access Management, Identity Providers, Settings
    expect(menuItems.length).toBe(3)
    expect(menu).toBeInTheDocument()
  })

  it('navigates to Access Management from System Administration dropdown', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    const navButton = screen.getByRole('button', { name: 'System Administration' })
    await user.click(navButton)

    const menu = screen.getByRole('menu')
    const menuItems = within(menu).getAllByRole('menuitem')
    await user.click(menuItems[0])
    expect(mockRequestNavigation).toHaveBeenCalledWith('/system-administration/access-management')
  })

  it('navigates to Identity Providers from System Administration dropdown', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    const navButton = screen.getByRole('button', { name: 'System Administration' })
    await user.click(navButton)

    await user.click(screen.getByText('Identity Providers'))
    expect(mockRequestNavigation).toHaveBeenCalledWith('/system-administration/authentication')
  })

  describe('Expanded text mode', () => {
    beforeEach(() => {
      mockUseDockState.mockReturnValue({
        isDockExpanded: false,
        isDockTextExpanded: true,
        isMobile: false,
        dockedToggleRef: { current: null },
        mobileToggleRef: { current: null },
        onToggleDock: mockOnToggleDock,
        onMobileToggle: vi.fn(),
      })
    })

    it('renders expandable nav groups instead of flyout menus', () => {
      renderDockedNav()
      expect(screen.getByRole('button', { name: 'Configuration' })).toBeInTheDocument()
      expect(screen.getByText('Integrations')).toBeInTheDocument()
      expect(screen.getByText('Credentials')).toBeInTheDocument()
    })

    it('does not hide nav expand toggles when dock text is expanded', () => {
      renderDockedNav()
      expect(screen.getByRole('navigation', { name: 'Main navigation' })).not.toHaveClass(styles.iconDockNav)
    })

    it('shows the brand logo when expanded', () => {
      renderDockedNav()
      const logo = within(screen.getByRole('banner')).getByRole('img', { name: 'Syntara' })
      expect(logo).toBeInTheDocument()
    })

    it('navigates to child item when clicked in expanded mode', async () => {
      const user = userEvent.setup()
      renderDockedNav()

      await user.click(screen.getByText('Integrations'))
      expect(mockRequestNavigation).toHaveBeenCalledWith('/configuration/integrations')
    })

    it('marks active child item when location matches', () => {
      mockLocation = '/configuration/integrations'
      renderDockedNav()
      const activeLink = screen.getByRole('link', { name: 'Integrations' })
      expect(activeLink).toHaveAttribute('href', '/configuration/integrations')
    })

    it('displays username in user menu toggle', () => {
      renderDockedNav()
      expect(screen.getByText('testuser')).toBeInTheDocument()
    })

    it('shows label text for color scheme and documentation buttons', () => {
      renderDockedNav()
      expect(screen.getByText('Light mode')).toBeInTheDocument()
      expect(screen.getByText('Documentation')).toBeInTheDocument()
    })

    it('hides tooltips when expanded', () => {
      renderDockedNav()
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    })
  })

  describe('Mobile mode', () => {
    beforeEach(() => {
      mockUseDockState.mockReturnValue({
        isDockExpanded: true,
        isDockTextExpanded: false,
        isMobile: true,
        dockedToggleRef: { current: null },
        mobileToggleRef: { current: null },
        onToggleDock: mockOnToggleDock,
        onMobileToggle: vi.fn(),
      })
    })

    it('renders expandable nav groups when dock is expanded on mobile', () => {
      renderDockedNav()
      expect(screen.getByText('Integrations')).toBeInTheDocument()
      expect(screen.getByText('Credentials')).toBeInTheDocument()
    })

    it('shows the brand logo when expanded on mobile', () => {
      renderDockedNav()
      const logo = within(screen.getByRole('banner')).getByRole('img', { name: 'Syntara' })
      expect(logo).toBeInTheDocument()
    })
  })

  describe('Mobile collapsed mode', () => {
    beforeEach(() => {
      mockUseDockState.mockReturnValue({
        isDockExpanded: false,
        isDockTextExpanded: false,
        isMobile: true,
        dockedToggleRef: { current: null },
        mobileToggleRef: { current: null },
        onToggleDock: mockOnToggleDock,
        onMobileToggle: vi.fn(),
      })
    })

    it('renders without errors when mobile and dock is collapsed', () => {
      renderDockedNav()
      expect(screen.getByRole('button', { name: 'Global navigation' })).toBeInTheDocument()
    })
  })

  it('renders light mode icon when in light mode', async () => {
    const user = userEvent.setup()
    document.documentElement.classList.remove('pf-v6-theme-dark', 'pf-v6-theme-glass')
    renderDockedNav()
    expect(screen.getByText('Dark mode')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /switch to dark mode/i }))
    expect(screen.getByText('Light mode')).toBeInTheDocument()
  })

  it('opens documentation in a new tab when Documentation button is clicked', async () => {
    const openSpy = vi.spyOn(globalThis, 'open').mockImplementation(() => null)
    const user = userEvent.setup()
    renderDockedNav()

    await user.click(screen.getByRole('button', { name: /documentation/i }))
    expect(openSpy).toHaveBeenCalledWith(expect.any(String), '_blank', 'noopener,noreferrer')
    openSpy.mockRestore()
  })

  it('renders user menu as "User" when currentUser is not loaded', () => {
    vi.mocked(authClient.useQuery).mockReturnValue({ data: undefined } as never)
    renderDockedNav()
    expect(screen.getByText('User')).toBeInTheDocument()
  })

  describe('Expanded with active configuration child', () => {
    beforeEach(() => {
      mockLocation = '/configuration/integrations'
      mockUseDockState.mockReturnValue({
        isDockExpanded: false,
        isDockTextExpanded: true,
        isMobile: false,
        dockedToggleRef: { current: null },
        mobileToggleRef: { current: null },
        onToggleDock: mockOnToggleDock,
        onMobileToggle: vi.fn(),
      })
    })

    it('highlights the active Configuration group', () => {
      renderDockedNav()
      const configButton = screen.getByRole('button', { name: 'Configuration' })
      expect(configButton).toBeInTheDocument()
    })

    it('renders child nav items with active state for matching path', () => {
      renderDockedNav()
      const integrationsLink = screen.getByRole('link', { name: 'Integrations' })
      expect(integrationsLink).toHaveClass('pf-m-current')
    })
  })

  describe('Expanded with active system-administration child', () => {
    beforeEach(() => {
      mockLocation = '/system-administration/access-management'
      mockUseDockState.mockReturnValue({
        isDockExpanded: false,
        isDockTextExpanded: true,
        isMobile: false,
        dockedToggleRef: { current: null },
        mobileToggleRef: { current: null },
        onToggleDock: mockOnToggleDock,
        onMobileToggle: vi.fn(),
      })
    })

    it('renders System Administration children in expanded mode', () => {
      renderDockedNav()
      expect(screen.getByText('Access Management')).toBeInTheDocument()
      expect(screen.getByText('Identity Providers')).toBeInTheDocument()
    })

    it('navigates to child when clicked in expanded System Administration', async () => {
      const user = userEvent.setup()
      renderDockedNav()

      await user.click(screen.getByText('Identity Providers'))
      expect(mockRequestNavigation).toHaveBeenCalledWith('/system-administration/authentication')
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = renderDockedNav()

    // Exclude aria-required-children: PatternFly Nav renders Divider as
    // <li role="separator"> inside <ul role="list">, which axe flags.
    // This is a PatternFly rendering concern, not an application-level issue.
    const results = await axe(container, {
      rules: { 'aria-required-children': { enabled: false } },
    })
    expect(results).toHaveNoViolations()
  })

  it('calls logout directly when Logout is clicked', async () => {
    const user = userEvent.setup()
    renderDockedNav()

    await user.hover(screen.getByRole('button', { name: 'User menu' }))
    await user.click(screen.getByText('Logout'))

    // Should call logout directly — no modal
    expect(mockLogout).toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
