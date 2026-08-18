import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { usersClient } from '../../../../client'
import { APP_TITLE } from '../../../../utils/appTitle'
import * as generateUUIDModule from '../../../../utils/generateUUID'
import { useAllGroups } from '../../../access/useAllGroups'

import { GroupMappingStep } from './GroupMappingStep'
import type { IdentityProviderFormData } from './identityProviderFormSchema'

vi.mock('../../../../client', () => ({
  usersClient: {
    useQuery: vi.fn(),
  },
  OIDC_AUTHORIZE_PATH: '/api/v1/auth/oidc/authorize',
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../access/useAllGroups', () => ({
  useAllGroups: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const mockMappedGroups = [
  { id: 'g1', name: 'admin' },
  { id: 'g2', name: 'users' },
]

const mockAllGroups = mockMappedGroups.map((g) => ({
  ...g,
  description: null,
  is_builtin: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}))

function TestWrapper({
  providerId,
  children,
}: {
  providerId?: string
  children?: (methods: {
    control: ReturnType<typeof useForm<IdentityProviderFormData>>['control']
    setValue: ReturnType<typeof useForm<IdentityProviderFormData>>['setValue']
  }) => ReactNode
}) {
  const methods = useForm<IdentityProviderFormData>({
    defaultValues: {
      groupMapping: { jmespathExpression: 'groups[*]', entries: [] },
    },
  })

  return (
    <QueryClientProvider client={queryClient}>
      <FormProvider {...methods}>
        {children ? (
          children({ control: methods.control, setValue: methods.setValue })
        ) : (
          <GroupMappingStep control={methods.control} setValue={methods.setValue} providerId={providerId} />
        )}
      </FormProvider>
    </QueryClientProvider>
  )
}

describe('GroupMappingStep', () => {
  beforeEach(() => {
    vi.mocked(useAllGroups).mockReturnValue({
      groups: mockAllGroups,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: mockMappedGroups },
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    } as never)
  })

  describe('Rendering', () => {
    it('renders group mapping section', () => {
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      expect(screen.getByText('Group mapping')).toBeInTheDocument()
    })

    it('renders Add mapping button', () => {
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      expect(screen.getByRole('button', { name: /add mapping/i })).toBeInTheDocument()
    })

    it('renders Discover groups button when providerId is set', () => {
      render(
        <TestWrapper>
          {({ control, setValue }) => (
            <GroupMappingStep control={control} setValue={setValue} providerId="provider-123" />
          )}
        </TestWrapper>
      )

      expect(screen.getByRole('button', { name: /discover groups/i })).toBeInTheDocument()
    })

    it('hides Discover groups button when no providerId', () => {
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      expect(screen.queryByRole('button', { name: /discover groups/i })).not.toBeInTheDocument()
    })

    it('renders advanced expandable section', () => {
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      expect(screen.getByText(/advanced/i)).toBeInTheDocument()
    })
  })

  describe('Adding mapping entries', () => {
    it('adds a mapping row when Add mapping is clicked', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /add mapping/i }))

      // Column headers appear
      expect(screen.getByText('IdP group value')).toBeInTheDocument()
      expect(screen.getByText(`${APP_TITLE} group`)).toBeInTheDocument()
      // Input for the new row
      expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeInTheDocument()
    })

    it('removes a mapping row when remove button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      // Add a row
      await user.click(screen.getByRole('button', { name: /add mapping/i }))
      expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeInTheDocument()

      // Remove it
      await user.click(screen.getByRole('button', { name: 'Remove mapping 1' }))
      expect(screen.queryByRole('textbox', { name: 'IdP group value 1' })).not.toBeInTheDocument()
    })
  })

  describe('JMESPath expression', () => {
    it('shows JMESPath input when advanced section is expanded', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      await user.click(screen.getByText(/advanced/i))

      expect(screen.getByLabelText('Group extraction expression')).toBeInTheDocument()
      expect(screen.getByLabelText('Group extraction expression')).toHaveValue('groups[*]')
    })
  })

  describe('Discover groups', () => {
    const TEST_NONCE = 'test-uuid'
    let originalOpen: typeof globalThis.open

    beforeEach(() => {
      originalOpen = globalThis.open
      vi.spyOn(generateUUIDModule, 'generateUUID').mockReturnValue(TEST_NONCE)
    })

    afterEach(() => {
      globalThis.open = originalOpen
      vi.restoreAllMocks()
    })

    it('opens a popup window when Discover groups is clicked', async () => {
      const mockOpen = vi.fn()
      globalThis.open = mockOpen

      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => (
            <GroupMappingStep control={control} setValue={setValue} providerId="provider-123" />
          )}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /discover groups/i }))

      expect(mockOpen).toHaveBeenCalledWith(
        expect.stringContaining('provider_id=provider-123'),
        'test-signin',
        expect.any(String)
      )
    })

    it('hides Discover groups button when no providerId', () => {
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      expect(screen.queryByRole('button', { name: /discover groups/i })).not.toBeInTheDocument()
    })

    it('discovers groups from storage event and shows success alert', async () => {
      const mockOpen = vi.fn().mockReturnValue({ closed: false })
      globalThis.open = mockOpen

      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => (
            <GroupMappingStep control={control} setValue={setValue} providerId="provider-123" />
          )}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /discover groups/i }))

      // Simulate the popup writing claims to localStorage (picked up by polling)
      const claims = { groups: ['admin', 'users'] }
      localStorage.setItem('syntara-test-signin', JSON.stringify({ type: 'test-signin', nonce: TEST_NONCE, claims }))

      // Should show success alert with discovered groups
      expect(await screen.findByRole('heading', { name: /groups discovered/i })).toBeInTheDocument()
    })

    it('shows warning when no groups are found from test sign-in', async () => {
      const mockOpen = vi.fn().mockReturnValue({ closed: false })
      globalThis.open = mockOpen

      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => (
            <GroupMappingStep control={control} setValue={setValue} providerId="provider-123" />
          )}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /discover groups/i }))

      // Simulate the popup writing claims with no groups
      const claims = { roles: ['admin'] } // no 'groups' key
      localStorage.setItem('syntara-test-signin', JSON.stringify({ type: 'test-signin', nonce: TEST_NONCE, claims }))

      expect(await screen.findByRole('heading', { name: /no groups found/i })).toBeInTheDocument()
    })

    it('ignores storage events with wrong key', async () => {
      const mockOpen = vi.fn().mockReturnValue({ closed: true })
      globalThis.open = mockOpen

      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => (
            <GroupMappingStep control={control} setValue={setValue} providerId="provider-123" />
          )}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /discover groups/i }))

      // Simulate storage event with wrong key
      const storageEvent = new StorageEvent('storage', {
        key: 'other-key',
        newValue: 'some value',
      })
      act(() => {
        globalThis.dispatchEvent(storageEvent)
      })

      // No alert should appear
      expect(screen.queryByText(/groups discovered/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/no groups found/i)).not.toBeInTheDocument()
    })

    it('ignores storage events with invalid JSON', async () => {
      const mockOpen = vi.fn().mockReturnValue({ closed: true })
      globalThis.open = mockOpen

      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => (
            <GroupMappingStep control={control} setValue={setValue} providerId="provider-123" />
          )}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /discover groups/i }))

      const storageEvent = new StorageEvent('storage', {
        key: 'syntara-test-signin',
        newValue: 'not-valid-json',
      })
      act(() => {
        globalThis.dispatchEvent(storageEvent)
      })

      expect(screen.queryByText(/groups discovered/i)).not.toBeInTheDocument()
    })
  })

  describe('Multiple mapping entries', () => {
    it('adds multiple mapping rows', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /add mapping/i }))
      await user.click(screen.getByRole('button', { name: /add mapping/i }))

      expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: 'IdP group value 2' })).toBeInTheDocument()
    })

    it('fills in IdP group value', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /add mapping/i }))
      const idpInput = screen.getByRole('textbox', { name: 'IdP group value 1' })
      await user.type(idpInput, 'admin-group')
      expect(idpInput).toHaveValue('admin-group')
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with mapping rows', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <TestWrapper>
          {({ control, setValue }) => <GroupMappingStep control={control} setValue={setValue} />}
        </TestWrapper>
      )

      await user.click(screen.getByRole('button', { name: /add mapping/i }))

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
