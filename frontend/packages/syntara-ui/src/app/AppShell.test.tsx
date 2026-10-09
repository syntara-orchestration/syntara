import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AppShell } from './AppShell'

vi.mock('../hooks/useRouteChangeFocus', () => ({
  useRouteChangeFocus: vi.fn(),
}))

vi.mock('../providers/unsaved-changes/UnsavedChangesProvider', () => ({
  UnsavedChangesProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="unsaved-changes-provider">{children}</div>
  ),
}))

vi.mock('./AppLogin', () => ({
  AppLogin: ({ children }: { children: React.ReactNode }) => <div data-testid="app-login">{children}</div>,
}))

vi.mock('../components/session/SessionTimeoutWarning', () => ({
  SessionTimeoutWarning: () => <div data-testid="session-timeout-warning" />,
}))

vi.mock('./AppDockedNav', () => ({
  AppDockedNav: () => <nav data-testid="app-docked-nav" />,
}))

vi.mock('./AppMobileMasthead', () => ({
  AppMobileMasthead: () => <div data-testid="mobile-masthead" />,
}))

vi.mock('../components/command-palette/CommandPaletteProvider', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="command-palette-provider">{children}</div>
  ),
}))

vi.mock('./useDockState', () => ({
  DockStateContext: { Provider: ({ children }: { children: React.ReactNode }) => children },
  useDockStateProvider: () => ({
    isDockExpanded: false,
    isDockTextExpanded: false,
    isMobile: false,
    dockedToggleRef: { current: null },
    mobileToggleRef: { current: null },
    onToggleDock: vi.fn(),
    onMobileToggle: vi.fn(),
  }),
}))

vi.mock('@patternfly/react-core', async () => {
  const actual = await vi.importActual<typeof import('@patternfly/react-core')>('@patternfly/react-core')
  return {
    ...actual,
    Compass: ({ dock, main }: { dock: React.ReactNode; main: React.ReactNode; className?: string }) => (
      <div data-testid="compass">
        {dock}
        {main}
      </div>
    ),
    CompassContent: ({
      children,
      role,
      ...props
    }: {
      children: React.ReactNode
      role?: string
      tabIndex?: number
      className?: string
    }) => (
      <div data-testid="compass-content" role={role} tabIndex={props.tabIndex} className={props.className}>
        {children}
      </div>
    ),
  }
})

describe('AppShell', () => {
  it('renders children inside the shell structure', () => {
    render(
      <AppShell>
        <div data-testid="child-content">Page content</div>
      </AppShell>
    )

    expect(screen.getByTestId('unsaved-changes-provider')).toBeInTheDocument()
    expect(screen.getByTestId('app-login')).toBeInTheDocument()
    expect(screen.getByTestId('session-timeout-warning')).toBeInTheDocument()
    expect(screen.getByTestId('app-docked-nav')).toBeInTheDocument()
    expect(screen.getByTestId('child-content')).toBeInTheDocument()
  })

  it('renders children within a main content area', () => {
    render(
      <AppShell>
        <div>Page content</div>
      </AppShell>
    )

    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveTextContent('Page content')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <AppShell>
        <div>Accessible content</div>
      </AppShell>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
