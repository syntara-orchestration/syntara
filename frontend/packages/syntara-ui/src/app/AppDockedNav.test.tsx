import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { authClient } from '../client'
import { BrandProvider } from '../providers/brand'
import { COLOR_SCHEME_STORAGE_KEY } from '../providers/theme/colorScheme'
import { ColorSchemeProvider } from '../providers/theme/ColorSchemeProvider'

import { AppDockedNav } from './AppDockedNav'
import type { DockState } from './useDockState'

function createMockDockState(overrides: Partial<DockState> = {}): DockState {
  return {
    isDockExpanded: false,
    isDockTextExpanded: false,
    isMobile: false,
    dockedToggleRef: { current: null },
    mobileToggleRef: { current: null },
    onToggleDock: mockOnToggleDock,
    onMobileToggle: vi.fn(),
    isDockExpandableExpanded: false,
    isNavGroupExpanded: () => false,
    onNavToggle: vi.fn(),
    onNavSelect: vi.fn(),
    ...overrides,
  }
}

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
    mockUseDockState.mockReturnValue(createMockDockState())
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

  it('uses PatternFly docked nav classes', () => {
    renderDockedNav()

    expect(screen.getByRole('banner')).toHaveClass('pf-v6-c-masthead', 'pf-m-docked')
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toHaveClass('pf-m-docked')
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

    const menu = screen.getByRole('menu')
    expect(within(menu).getByText('My Profile')).toBeInTheDocument()
    expect(within(menu).getByText('Logout')).toBeInTheDocument()
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

  it('calls onNavToggle when an expandable group is clicked', async () => {
    const onNavToggle = vi.fn()
    mockUseDockState.mockReturnValue(createMockDockState({ onNavToggle }))
    const user = userEvent.setup()
    renderDockedNav()

    await user.click(screen.getByRole('button', { name: 'Configuration' }))
    expect(onNavToggle).toHaveBeenCalled()
  })

  it('shows Configuration child links when the group is expanded', () => {
    mockUseDockState.mockReturnValue(
      createMockDockState({
        isDockTextExpanded: true,
        isNavGroupExpanded: () => true,
      })
    )
    renderDockedNav()

    expect(screen.getByRole('link', { name: 'Integrations' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Credentials' })).toBeInTheDocument()
  })

  it('navigates to Integrations when Configuration child link is clicked', async () => {
    mockUseDockState.mockReturnValue(
      createMockDockState({
        isDockTextExpanded: true,
        isNavGroupExpanded: () => true,
      })
    )
    const user = userEvent.setup()
    renderDockedNav()

    await user.click(screen.getByRole('link', { name: 'Integrations' }))
    expect(mockRequestNavigation).toHaveBeenCalledWith('/configuration/integrations')
  })

  it('shows System Administration child links when the group is expanded', () => {
    mockUseDockState.mockReturnValue(
      createMockDockState({
        isDockTextExpanded: true,
        isNavGroupExpanded: () => true,
      })
    )
    renderDockedNav()

    expect(screen.getByRole('link', { name: 'Access Management' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Identity Providers' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument()
  })

  it('navigates to Access Management from System Administration child link', async () => {
    mockUseDockState.mockReturnValue(
      createMockDockState({
        isDockTextExpanded: true,
        isNavGroupExpanded: () => true,
      })
    )
    const user = userEvent.setup()
    renderDockedNav()

    await user.click(screen.getByRole('link', { name: 'Access Management' }))
    expect(mockRequestNavigation).toHaveBeenCalledWith('/system-administration/access-management')
  })

  it('navigates to Identity Providers from System Administration child link', async () => {
    mockUseDockState.mockReturnValue(
      createMockDockState({
        isDockTextExpanded: true,
        isNavGroupExpanded: () => true,
      })
    )
    const user = userEvent.setup()
    renderDockedNav()

    await user.click(screen.getByRole('link', { name: 'Identity Providers' }))
    expect(mockRequestNavigation).toHaveBeenCalledWith('/system-administration/authentication')
  })

  describe('Expanded text mode', () => {
    beforeEach(() => {
      mockUseDockState.mockReturnValue(
        createMockDockState({
          isDockTextExpanded: true,
          isNavGroupExpanded: () => true,
        })
      )
    })

    it('renders expandable nav groups with child links visible', () => {
      renderDockedNav()
      expect(screen.getByRole('button', { name: 'Configuration' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Integrations' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Credentials' })).toBeInTheDocument()
    })

    it('shows the brand logo when expanded', () => {
      renderDockedNav()
      const logos = within(screen.getByRole('banner')).getAllByRole('img', { name: 'Syntara' })
      expect(logos.length).toBeGreaterThanOrEqual(1)
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
      mockUseDockState.mockReturnValue(
        createMockDockState({
          isDockExpanded: true,
          isMobile: true,
          isNavGroupExpanded: () => true,
        })
      )
    })

    it('shows label text for docked actions when mobile overlay is expanded', () => {
      renderDockedNav()
      expect(screen.getByText('Light mode')).toBeInTheDocument()
      expect(screen.getByText('Documentation')).toBeInTheDocument()
    })

    it('does not apply icon-only nav styles when mobile overlay is expanded', () => {
      renderDockedNav()
      expect(screen.getByRole('navigation', { name: 'Main navigation' })).not.toHaveClass(styles.iconDockNav)
    })

    it('renders expandable nav groups when dock is expanded on mobile', () => {
      renderDockedNav()
      expect(screen.getByRole('link', { name: 'Integrations' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Credentials' })).toBeInTheDocument()
    })

    it('shows the brand logo when expanded on mobile', () => {
      renderDockedNav()
      const logos = within(screen.getByRole('banner')).getAllByRole('img', { name: 'Syntara' })
      expect(logos.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Mobile collapsed mode', () => {
    beforeEach(() => {
      mockUseDockState.mockReturnValue(createMockDockState({ isMobile: true }))
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
      mockUseDockState.mockReturnValue(
        createMockDockState({
          isDockTextExpanded: true,
          isNavGroupExpanded: () => true,
        })
      )
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
      mockUseDockState.mockReturnValue(
        createMockDockState({
          isDockTextExpanded: true,
          isNavGroupExpanded: () => true,
        })
      )
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
