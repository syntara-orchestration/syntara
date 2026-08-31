import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AppRoute } from '../../app/AppRoute'
import { adminClient, usersClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import { routerTestState } from '../../test/setup'
import { accessClient, accessFetchClient } from '../access/accessClient'

import { AccessManagement } from './AccessManagement'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

vi.mock('../../client', () => ({
  usersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  adminClient: {
    useMutation: vi.fn().mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    }),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

describe('AccessManagement', () => {
  beforeEach(() => {
    queryClient.clear()
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    } as never)
    vi.mocked(usersClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    } as never)
    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
    vi.mocked(adminClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    routerTestState.pathname = AppRoute.AccessManagement.Users
  })

  async function renderAndSettle(ui: React.ReactElement) {
    const view = render(ui, { wrapper })
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Access Management' })).toBeInTheDocument()
      expect(screen.queryAllByRole('tab').length).toBeGreaterThan(0)
    })
    return view
  }

  it('renders the page header', async () => {
    await renderAndSettle(<AccessManagement />)

    expect(screen.getByRole('heading', { name: 'Access Management' })).toBeInTheDocument()
  })

  it('renders all expected tabs', async () => {
    await renderAndSettle(<AccessManagement />)

    expect(screen.getByRole('tab', { name: 'Users' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Groups' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Policies' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Roles' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Assignments' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Check access' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Token revocation' })).toBeInTheDocument()
  })

  it('hides Token revocation tab when user lacks token-revocation:read permission', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string, options: never) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      const { body } = options as { body: { resource_type: string } }
      if (body.resource_type === 'admin:revocation') return Promise.resolve({ data: { allowed: false } } as never)
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      expect(screen.queryByRole('tab', { name: 'Token revocation' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'Users' })).toBeInTheDocument()
  })

  it('does not render Identity Providers or Claim Mappings tabs', async () => {
    await renderAndSettle(<AccessManagement />)

    expect(screen.queryByRole('tab', { name: 'Identity Providers' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Claim Mappings' })).not.toBeInTheDocument()
  })

  it('defaults to Users tab', async () => {
    await renderAndSettle(<AccessManagement />)

    expect(screen.getByText('No users yet')).toBeInTheDocument()
  })

  it('replaces bare /system-administration/access-management with the Users tab URL', async () => {
    routerTestState.pathname = AppRoute.AccessManagement.Root
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: AppRoute.AccessManagement.Users, replace: true })
    })
  })

  it('renders breadcrumbs on all tabs including Users', async () => {
    await renderAndSettle(<AccessManagement />)

    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument()
  })

  it('renders breadcrumbs on non-default hub tabs', async () => {
    routerTestState.pathname = AppRoute.AccessManagement.Groups
    await renderAndSettle(<AccessManagement />)

    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Access management' })).toBeInTheDocument()
  })

  it('defaults to first tab when location does not match any tab path', async () => {
    routerTestState.pathname = '/access-management/unknown-path'
    await renderAndSettle(<AccessManagement />)

    expect(screen.getByText('No users yet')).toBeInTheDocument()
  })

  it('navigates to Groups tab when clicked', async () => {
    const user = userEvent.setup()
    await renderAndSettle(<AccessManagement />)

    await user.click(screen.getByRole('tab', { name: 'Groups' }))

    // SynListPanelTabs uses useNavigate (via useUrlTab) for tab navigation
    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: AppRoute.AccessManagement.Groups })
  })

  it('hides Users tab when user lacks user:read permission', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string, options: never) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      const { body } = options as { body: { resource_type: string } }
      if (body.resource_type === 'user') return Promise.resolve({ data: { allowed: false } } as never)
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    routerTestState.pathname = AppRoute.AccessManagement.Groups
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      expect(screen.queryByRole('tab', { name: 'Users' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'Groups' })).toBeInTheDocument()
  })

  it('hides Groups tab when user lacks group:read permission', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string, options: never) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      const { body } = options as { body: { resource_type: string } }
      if (body.resource_type === 'group') return Promise.resolve({ data: { allowed: false } } as never)
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      expect(screen.queryByRole('tab', { name: 'Groups' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'Users' })).toBeInTheDocument()
  })

  it('hides Projects tab when user lacks project:read permission', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string, options: never) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      const { body } = options as { body: { resource_type: string } }
      if (body.resource_type === 'project') return Promise.resolve({ data: { allowed: false } } as never)
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      expect(screen.queryByRole('tab', { name: 'Projects' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'Users' })).toBeInTheDocument()
  })

  it('hides Assignments tab when user lacks role-assignment:read permission', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string, options: never) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      const { body } = options as { body: { resource_type: string } }
      if (body.resource_type === 'role-assignment') return Promise.resolve({ data: { allowed: false } } as never)
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      expect(screen.queryByRole('tab', { name: 'Assignments' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'Users' })).toBeInTheDocument()
  })

  it('shows Roles, Policies, and Check access when system grants remain', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string, options: never) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      const { body } = options as { body: { resource_type: string } }
      if (['user', 'group', 'project'].includes(body.resource_type)) {
        return Promise.resolve({ data: { allowed: false } } as never)
      }
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    routerTestState.pathname = AppRoute.AccessManagement.Policies
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      expect(screen.queryByRole('tab', { name: 'Users' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'Policies' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Roles' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Check access' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Assignments' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Groups' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Projects' })).not.toBeInTheDocument()
  })

  it('hides Roles and Policies tabs without system role/policy read', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((_path: string, options: never) => {
      const { body } = options as {
        body: { action: string; resource_type: string; check_any_project?: boolean }
      }
      // Project-admin: any-project grants for assignments/projects only
      if (
        body.check_any_project === true &&
        ((body.resource_type === 'role-assignment' && body.action === 'read') ||
          (body.resource_type === 'project' && body.action === 'read'))
      ) {
        return Promise.resolve({ data: { allowed: true } } as never)
      }
      return Promise.resolve({ data: { allowed: false } } as never)
    })
    routerTestState.pathname = AppRoute.AccessManagement.Assignments
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Assignments' })).toBeInTheDocument()
    })
    expect(screen.queryByRole('tab', { name: 'Roles' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Policies' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Users' })).not.toBeInTheDocument()
  })

  it('redirects to first allowed tab when navigating to a restricted path', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string, options: never) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      const { body } = options as { body: { resource_type: string } }
      if (body.resource_type === 'user') return Promise.resolve({ data: { allowed: false } } as never)
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    routerTestState.pathname = AppRoute.AccessManagement.Users
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      // useUrlTab uses useNavigate for tab redirects
      expect(routerTestState.navigate).toHaveBeenCalledWith(
        expect.objectContaining({ to: AppRoute.AccessManagement.Groups })
      )
    })
  })

  it('redirects from hidden Projects tab to first allowed tab', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((path: string, options: never) => {
      if (path === '/authz/what_can_i') {
        return Promise.resolve({ data: { resources: [], next: null } } as never)
      }
      const { body } = options as { body: { resource_type: string } }
      if (body.resource_type === 'project') return Promise.resolve({ data: { allowed: false } } as never)
      return Promise.resolve({ data: { allowed: true } } as never)
    })
    routerTestState.pathname = AppRoute.AccessManagement.Projects
    await renderAndSettle(<AccessManagement />)

    await waitFor(() => {
      // SynUrlTabs redirects via navigate({ to, replace: true }) when the active tab is hidden
      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: AppRoute.AccessManagement.Users, replace: true })
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = await renderAndSettle(<AccessManagement />)

    // Wrap axe in act() -- axe triggers DOM events (focus, scroll) that
    // cause PatternFly Tabs to schedule React state updates
    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      // Exclude aria-valid-attr-value: PatternFly Tabs generates aria-controls
      // referencing lazily-rendered tab panels that don't exist in the DOM yet
      results = await axe(container, {
        rules: { 'aria-valid-attr-value': { enabled: false } },
      })
    })
    expect(results!).toHaveNoViolations()
  })

  describe('no access', () => {
    function denyAllAccess() {
      vi.mocked(accessFetchClient.POST).mockImplementation((path: string) => {
        if (path === '/authz/what_can_i') {
          return Promise.resolve({ data: { resources: [], next: null } } as never)
        }
        return Promise.resolve({ data: { allowed: false } } as never)
      })
    }

    it('shows access denied when user lacks all AM permissions', async () => {
      denyAllAccess()

      render(<AccessManagement />, { wrapper })

      await waitFor(() => {
        expect(screen.getByText('Access denied')).toBeInTheDocument()
      })
      expect(screen.getByRole('heading', { name: 'Access Management' })).toBeInTheDocument()
      expect(screen.getByText(/You don't have permission to view access management/)).toBeInTheDocument()
      expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    })

    it('has no accessibility violations in access denied state', async () => {
      denyAllAccess()

      const { container } = render(<AccessManagement />, { wrapper })

      await waitFor(() => {
        expect(screen.getByText('Access denied')).toBeInTheDocument()
      })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
