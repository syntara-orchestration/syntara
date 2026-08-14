import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { usersClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'
import { routerTestState } from '../../../../test/setup'
import { useAllGroups } from '../../../access/useAllGroups'

import { GroupMappingTab } from './GroupMappingTab'

vi.mock('../../../../client', () => ({
  identityProvidersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  usersClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../access/useAllGroups', () => ({
  useAllGroups: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockNexusGroups = [
  { id: 'g1', name: 'admin', description: 'Admins', created_at: '2026-01-01T00:00:00Z' },
  { id: 'g2', name: 'users', description: 'Users', created_at: '2026-01-02T00:00:00Z' },
]

const defaultProps = {
  providerId: 'provider-123',
  groupMapping: null,
}

describe('GroupMappingTab', () => {
  beforeEach(() => {
    routerTestState.navigate.mockClear()
    vi.mocked(useAllGroups).mockReturnValue({
      groups: mockNexusGroups.map((g) => ({
        ...g,
        is_builtin: false,
        updated_at: g.created_at,
      })),
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: mockNexusGroups },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    } as never)
  })

  describe('Empty state', () => {
    it('shows empty mapping state when no group mappings exist', () => {
      render(<GroupMappingTab {...defaultProps} />, { wrapper })

      expect(screen.getByRole('heading', { name: /no group mappings configured/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /discover groups/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /add manually/i })).toBeInTheDocument()
    })

    it('navigates to edit page with new=1 when Add manually is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupMappingTab {...defaultProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: /add manually/i }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/authentication/identity-providers/provider-123/group-mapping/edit?new=1',
      })
    })

    it('navigates to edit page with discover=1 when Discover groups is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupMappingTab {...defaultProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: /discover groups/i }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/authentication/identity-providers/provider-123/group-mapping/edit?discover=1',
      })
    })
  })

  describe('Read-only view', () => {
    const existingMapping = {
      group_jmespath_expression: 'groups[*]',
      group_mapping_entries: [
        { idp_group_value: 'idp-admin', mapped_group_id: 'g1' },
        { idp_group_value: 'idp-users', mapped_group_id: 'g2' },
      ],
    }

    it('shows read-only view when mappings exist', () => {
      render(<GroupMappingTab {...defaultProps} groupMapping={existingMapping} />, { wrapper })

      expect(screen.getByPlaceholderText('Filter by keyword')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /edit group mapping/i })).toBeInTheDocument()
      expect(screen.getByText('idp-admin')).toBeInTheDocument()
    })

    it('navigates to edit page when Edit group mapping is clicked', async () => {
      const user = userEvent.setup()
      render(<GroupMappingTab {...defaultProps} groupMapping={existingMapping} />, { wrapper })

      await user.click(screen.getByRole('button', { name: /edit group mapping/i }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/authentication/identity-providers/provider-123/group-mapping/edit',
      })
    })
  })

  describe('Read-only permission mode', () => {
    it('hides empty-state actions when readOnly', () => {
      render(<GroupMappingTab {...defaultProps} readOnly />, { wrapper })

      expect(screen.getByRole('heading', { name: /no group mappings configured/i })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /discover groups/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /add manually/i })).not.toBeInTheDocument()
    })

    it('hides Edit group mapping when readOnly and mappings exist', () => {
      const existingMapping = {
        group_mapping_entries: [{ idp_group_value: 'idp-admin', mapped_group_id: 'g1' }],
      }
      render(<GroupMappingTab {...defaultProps} groupMapping={existingMapping} readOnly />, { wrapper })

      expect(screen.getByPlaceholderText('Filter by keyword')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /edit group mapping/i })).not.toBeInTheDocument()
      expect(screen.getByText('idp-admin')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations in empty state', async () => {
      const { container } = render(<GroupMappingTab {...defaultProps} />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in read-only view', async () => {
      const existingMapping = {
        group_mapping_entries: [{ idp_group_value: 'admin', mapped_group_id: 'g1' }],
      }
      const { container } = render(<GroupMappingTab {...defaultProps} groupMapping={existingMapping} />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
