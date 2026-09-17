import { zodResolver } from '@hookform/resolvers/zod'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { groupMappingEditFormSchema } from './groupMappingEditFormSchema'
import { GroupMappingEditPanel, type GroupMappingEditPanelProps } from './GroupMappingEditPanel'

vi.mock('../../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(() => ({ data: undefined, isLoading: false, error: null })),
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  },
  accessFetchClient: { POST: vi.fn() },
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const MOCK_GROUP_ID = 'b1b2c3d4-e5f6-7890-abcd-ef1234567891'

const defaultPanelProps: Omit<GroupMappingEditPanelProps, 'control'> = {
  signInAlert: null,
  onDismissSignInAlert: () => undefined,
  mappingRows: [{ rowId: 'e1', index: 0 }],
  mappedGroups: [{ id: MOCK_GROUP_ID, name: 'admin' }],
  onRemove: () => undefined,
  onAdd: () => undefined,
  onCreateGroup: () => undefined,
  onReDiscover: () => undefined,
  isListening: false,
  defaultExpression: 'groups[*]',
  idpType: 'custom',
  rawClaims: null,
  createGroupForIndex: null,
  onCloseCreateGroup: () => undefined,
  onGroupCreated: () => undefined,
}

function EditPanelHarness(props: Partial<GroupMappingEditPanelProps> = {}) {
  const form = useForm({
    resolver: zodResolver(groupMappingEditFormSchema),
    defaultValues: {
      expression: 'groups[*]',
      entries: [{ idpGroupValue: 'admin', mappedGroupId: MOCK_GROUP_ID }],
    },
  })

  return (
    <FormProvider {...form}>
      <GroupMappingEditPanel {...defaultPanelProps} control={form.control} {...props} />
    </FormProvider>
  )
}

describe('GroupMappingEditPanel', () => {
  it('renders mapping table and re-discover control', () => {
    render(<EditPanelHarness />, { wrapper })
    expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-discover groups/i })).toBeInTheDocument()
  })

  it('renders and dismisses sign-in alert', async () => {
    const onDismissSignInAlert = vi.fn()
    const user = userEvent.setup()

    render(
      <EditPanelHarness
        signInAlert={{ variant: 'success', message: 'Mapped 2 groups.' }}
        onDismissSignInAlert={onDismissSignInAlert}
      />,
      { wrapper }
    )

    expect(screen.getByText('Mapped 2 groups.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /close/i }))
    expect(onDismissSignInAlert).toHaveBeenCalled()
  })

  it('renders warning sign-in alert title', () => {
    render(<EditPanelHarness signInAlert={{ variant: 'warning', message: 'No groups found in token.' }} />, { wrapper })

    expect(screen.getByText('No groups found')).toBeInTheDocument()
    expect(screen.getByText('No groups found in token.')).toBeInTheDocument()
  })

  it('renders danger sign-in alert title', () => {
    render(
      <EditPanelHarness signInAlert={{ variant: 'danger', message: 'Could not connect to the identity provider.' }} />,
      { wrapper }
    )

    expect(screen.getByText('Sign-in failed')).toBeInTheDocument()
    expect(screen.getByText('Could not connect to the identity provider.')).toBeInTheDocument()
  })

  it('shows waiting label while re-discover is in progress', () => {
    render(<EditPanelHarness isListening />, { wrapper })

    expect(screen.getByRole('button', { name: /waiting for sign-in/i })).toBeDisabled()
  })

  it('opens create group modal for selected row', () => {
    render(<EditPanelHarness createGroupForIndex={0} />, { wrapper })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<EditPanelHarness />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
