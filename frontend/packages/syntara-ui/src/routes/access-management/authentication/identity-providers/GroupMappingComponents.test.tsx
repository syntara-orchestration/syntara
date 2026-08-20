import { zodResolver } from '@hookform/resolvers/zod'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { APP_TITLE } from '../../../../utils/appTitle'

import {
  AdvancedSection,
  EmptyMappingState,
  GroupMappingFormActions,
  MappingTable,
  ReadOnlyView,
} from './GroupMappingComponents'
import type { MappingTableProps } from './GroupMappingComponents'
import { groupMappingEditFormSchema } from './groupMappingEditFormSchema'
import type { GroupMappingEntry, MappedGroup } from './groupMappingUtils'

const mockMappedGroups: MappedGroup[] = [
  { id: 'g1', name: 'admin', description: 'Administrators' },
  { id: 'g2', name: 'users', description: 'Regular users' },
]

const mockEntries: GroupMappingEntry[] = [
  { key: 'k1', idpGroupValue: 'idp-admin', mappedGroupId: 'g1' },
  { key: 'k2', idpGroupValue: 'idp-users', mappedGroupId: 'g2' },
]

describe('EmptyMappingState', () => {
  it('renders heading and description', () => {
    render(<EmptyMappingState onTestSignIn={vi.fn()} onAddManually={vi.fn()} />)

    expect(screen.getByRole('heading', { name: /no group mappings configured/i })).toBeInTheDocument()
    expect(screen.getByText(/automatically assign users/i)).toBeInTheDocument()
  })

  it('renders Discover groups and Add manually buttons', () => {
    render(<EmptyMappingState onTestSignIn={vi.fn()} onAddManually={vi.fn()} />)

    expect(screen.getByRole('button', { name: /discover groups/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add manually/i })).toBeInTheDocument()
  })

  it('calls onTestSignIn when Discover groups button is clicked', async () => {
    const onTestSignIn = vi.fn()
    const user = userEvent.setup()
    render(<EmptyMappingState onTestSignIn={onTestSignIn} onAddManually={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /discover groups/i }))
    expect(onTestSignIn).toHaveBeenCalledOnce()
  })

  it('calls onAddManually when Add manually button is clicked', async () => {
    const onAddManually = vi.fn()
    const user = userEvent.setup()
    render(<EmptyMappingState onTestSignIn={vi.fn()} onAddManually={onAddManually} />)

    await user.click(screen.getByRole('button', { name: /add manually/i }))
    expect(onAddManually).toHaveBeenCalledOnce()
  })

  it('hides action buttons when callbacks are omitted', () => {
    render(<EmptyMappingState />)

    expect(screen.getByRole('heading', { name: /no group mappings configured/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /discover groups/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add manually/i })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<EmptyMappingState onTestSignIn={vi.fn()} onAddManually={vi.fn()} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('AdvancedSection', () => {
  function AdvancedSectionHarness({
    defaultValues,
    ...props
  }: {
    defaultValues?: { expression: string; entries: { idpGroupValue: string; mappedGroupId: string }[] }
    defaultExpression: string | null
    idpType?: string | null
    rawClaims: string | null
  }) {
    const form = useForm({
      resolver: zodResolver(groupMappingEditFormSchema),
      defaultValues: defaultValues ?? { expression: 'groups[*]', entries: [] },
    })

    return (
      <FormProvider {...form}>
        <AdvancedSection control={form.control} {...props} />
      </FormProvider>
    )
  }

  const defaultProps = {
    defaultExpression: null as string | null,
    rawClaims: null as string | null,
  }

  it('renders expandable section with JMESPath label', () => {
    render(<AdvancedSectionHarness {...defaultProps} />)
    expect(screen.getByText('Advanced')).toBeInTheDocument()
  })

  it('shows expression input when expanded', async () => {
    const user = userEvent.setup()
    render(<AdvancedSectionHarness {...defaultProps} />)

    await user.click(screen.getByText('Advanced'))
    expect(screen.getByLabelText('Group extraction expression')).toBeInTheDocument()
  })

  it('updates expression when input is modified', async () => {
    const user = userEvent.setup()
    render(<AdvancedSectionHarness {...defaultProps} />)

    await user.click(screen.getByText('Advanced'))
    const input = screen.getByLabelText('Group extraction expression')
    await user.clear(input)
    await user.paste('custom[*]')

    expect(input).toHaveValue('custom[*]')
  })

  it('shows reset button when expression differs from default', async () => {
    const user = userEvent.setup()
    render(
      <AdvancedSectionHarness
        {...defaultProps}
        defaultValues={{ expression: 'custom[*]', entries: [] }}
        defaultExpression="groups[*]"
        idpType="custom"
      />
    )

    await user.click(screen.getByText('Advanced'))
    expect(screen.getByRole('button', { name: /reset to default/i })).toBeInTheDocument()
  })

  it('does not show reset button when expression matches default', async () => {
    const user = userEvent.setup()
    render(
      <AdvancedSectionHarness
        {...defaultProps}
        defaultValues={{ expression: 'groups[*]', entries: [] }}
        defaultExpression="groups[*]"
      />
    )

    await user.click(screen.getByText('Advanced'))
    expect(screen.queryByRole('button', { name: /reset to default/i })).not.toBeInTheDocument()
  })

  it('resets expression to default when reset is clicked', async () => {
    const user = userEvent.setup()
    render(
      <AdvancedSectionHarness
        {...defaultProps}
        defaultValues={{ expression: 'custom[*]', entries: [] }}
        defaultExpression="groups[*]"
      />
    )

    await user.click(screen.getByText('Advanced'))
    await user.click(screen.getByRole('button', { name: /reset to default/i }))
    expect(screen.getByLabelText('Group extraction expression')).toHaveValue('groups[*]')
  })

  it('shows validation error for invalid JMESPath after submit', async () => {
    const user = userEvent.setup()

    function SubmitHarness() {
      const form = useForm({
        resolver: zodResolver(groupMappingEditFormSchema),
        defaultValues: { expression: '[[[bad', entries: [] },
      })

      return (
        <FormProvider {...form}>
          <AdvancedSection control={form.control} defaultExpression={null} rawClaims={null} />
          <button type="button" onClick={() => form.handleSubmit(() => undefined)()}>
            Validate
          </button>
        </FormProvider>
      )
    }

    render(<SubmitHarness />)
    await user.click(screen.getByText('Advanced'))
    await user.click(screen.getByRole('button', { name: 'Validate' }))

    expect(screen.getByText(/Invalid group extraction expression/i)).toBeInTheDocument()
  })

  it('shows raw claims when provided', async () => {
    const user = userEvent.setup()
    const rawClaims = JSON.stringify({ groups: ['admin'] }, null, 2)
    render(<AdvancedSectionHarness {...defaultProps} rawClaims={rawClaims} />)

    await user.click(screen.getByText('Advanced'))
    expect(screen.getByText('Raw token claims')).toBeInTheDocument()
    expect(screen.getByText(/Full token claims from the last group discovery/)).toBeInTheDocument()
  })

  it('does not show raw claims section when null', async () => {
    const user = userEvent.setup()
    render(<AdvancedSectionHarness {...defaultProps} rawClaims={null} />)

    await user.click(screen.getByText('Advanced'))
    expect(screen.queryByText('Raw token claims')).not.toBeInTheDocument()
  })
})

describe('GroupMappingFormActions', () => {
  it('calls onAdd and onReDiscover from action buttons', async () => {
    const onAdd = vi.fn()
    const onReDiscover = vi.fn()
    const user = userEvent.setup()

    render(<GroupMappingFormActions onAdd={onAdd} onReDiscover={onReDiscover} isListening={false} />)

    await user.click(screen.getByRole('button', { name: /add mapping/i }))
    await user.click(screen.getByRole('button', { name: /re-discover groups/i }))

    expect(onAdd).toHaveBeenCalledOnce()
    expect(onReDiscover).toHaveBeenCalledOnce()
  })

  it('shows waiting state while listening for sign-in', () => {
    render(<GroupMappingFormActions onAdd={vi.fn()} onReDiscover={vi.fn()} isListening />)

    expect(screen.getByRole('button', { name: /waiting for sign-in/i })).toBeDisabled()
  })
})

const mockRows = [
  { rowId: 'k1', index: 0, idpGroupValue: 'idp-admin', mappedGroupId: 'g1' },
  { rowId: 'k2', index: 1, idpGroupValue: 'idp-users', mappedGroupId: 'g2' },
]

const editFormEntries = [
  { idpGroupValue: 'idp-admin', mappedGroupId: 'g1' },
  { idpGroupValue: 'idp-users', mappedGroupId: 'g2' },
]

function MappingTableFormHarness({
  rows = [
    { rowId: 'k1', index: 0 },
    { rowId: 'k2', index: 1 },
  ],
  entries = editFormEntries,
  ...tableProps
}: Omit<MappingTableProps, 'control' | 'rows'> & {
  rows?: MappingTableProps['rows']
  entries?: { idpGroupValue: string; mappedGroupId: string }[]
}) {
  const form = useForm({
    resolver: zodResolver(groupMappingEditFormSchema),
    defaultValues: { expression: 'groups[*]', entries },
  })

  return (
    <FormProvider {...form}>
      <MappingTable {...tableProps} rows={rows} control={form.control} />
    </FormProvider>
  )
}

describe('MappingTable', () => {
  const defaultProps = {
    mappedGroups: mockMappedGroups,
    onRemove: vi.fn(),
    onAdd: vi.fn(),
    onCreateGroup: vi.fn(),
  }

  it('renders column headers', () => {
    render(<MappingTableFormHarness {...defaultProps} />)

    expect(screen.getByText('IdP group value')).toBeInTheDocument()
    expect(screen.getByText(`${APP_TITLE} group`)).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'Group mappings' })).toHaveClass('pf-m-compact')
  })

  it('renders mapping entries with input values', () => {
    render(<MappingTableFormHarness {...defaultProps} />)

    expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toHaveValue('idp-admin')
    expect(screen.getByRole('textbox', { name: 'IdP group value 2' })).toHaveValue('idp-users')
  })

  it('renders Add mapping button when not read-only', () => {
    render(<MappingTableFormHarness {...defaultProps} />)
    expect(screen.getByRole('button', { name: /add mapping/i })).toBeInTheDocument()
  })

  it('hides Add mapping when showAddMappingAction is false', () => {
    render(<MappingTableFormHarness {...defaultProps} showAddMappingAction={false} />)
    expect(screen.queryByRole('button', { name: /add mapping/i })).not.toBeInTheDocument()
  })

  it('calls onAdd when Add mapping is clicked', async () => {
    const onAdd = vi.fn()
    const user = userEvent.setup()
    render(<MappingTableFormHarness {...defaultProps} onAdd={onAdd} />)

    await user.click(screen.getByRole('button', { name: /add mapping/i }))
    expect(onAdd).toHaveBeenCalledOnce()
  })

  it('renders remove buttons for each entry', () => {
    render(<MappingTableFormHarness {...defaultProps} />)

    expect(screen.getByRole('button', { name: 'Remove mapping 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove mapping 2' })).toBeInTheDocument()
  })

  it('calls onRemove with row index when remove button is clicked', async () => {
    const onRemove = vi.fn()
    const user = userEvent.setup()
    render(<MappingTableFormHarness {...defaultProps} onRemove={onRemove} />)

    await user.click(screen.getByRole('button', { name: 'Remove mapping 1' }))
    expect(onRemove).toHaveBeenCalledWith(0)
  })

  it('keeps IdP group value input focused while typing', async () => {
    const user = userEvent.setup()
    render(
      <MappingTableFormHarness
        {...defaultProps}
        rows={[{ rowId: 'k1', index: 0 }]}
        entries={[{ idpGroupValue: '', mappedGroupId: '' }]}
      />
    )

    const input = screen.getByRole('textbox', { name: 'IdP group value 1' })
    await user.click(input)
    await user.type(input, 'hello')

    expect(input).toHaveValue('hello')
    expect(input).toHaveFocus()
  })

  it('hides remove buttons, Add mapping, and form controls in read-only mode', () => {
    render(<MappingTable {...defaultProps} rows={mockRows} isReadOnly />)

    expect(screen.queryByRole('button', { name: 'Remove mapping 1' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add mapping/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'IdP group value 1' })).not.toBeInTheDocument()
    expect(screen.getByText('idp-admin')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<MappingTableFormHarness {...defaultProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('ReadOnlyView', () => {
  const readOnlyDefaults = {
    entries: mockEntries,
    mappedGroups: mockMappedGroups,
    onEditMapping: vi.fn(),
  }

  it('renders Edit group mapping button and keyword filter toolbar', () => {
    render(<ReadOnlyView {...readOnlyDefaults} />)

    expect(screen.getByRole('button', { name: /edit group mapping/i })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Filter by keyword')).toBeInTheDocument()
  })

  it('hides Edit group mapping when onEditMapping is omitted', () => {
    render(<ReadOnlyView entries={mockEntries} mappedGroups={mockMappedGroups} />)

    expect(screen.getByPlaceholderText('Filter by keyword')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit group mapping/i })).not.toBeInTheDocument()
  })

  it('renders entries as plain text in table cells', () => {
    render(<ReadOnlyView {...readOnlyDefaults} />)

    expect(screen.queryByRole('textbox', { name: 'IdP group value 1' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove mapping 1' })).not.toBeInTheDocument()
    expect(screen.getByText('idp-admin')).toBeInTheDocument()
    expect(screen.getByText('idp-users')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
    expect(screen.getByText('users')).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'Group mappings' })).toHaveClass('pf-m-compact')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ReadOnlyView {...readOnlyDefaults} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('shows EmptyStateNoData when there are no mappings', () => {
    render(<ReadOnlyView {...readOnlyDefaults} entries={[]} />)

    expect(screen.getByRole('heading', { name: /no group mappings/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit mapping/i })).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Filter by keyword')).not.toBeInTheDocument()
  })

  it('shows EmptyStateFilter when keyword filter matches no rows', async () => {
    const user = userEvent.setup()
    render(<ReadOnlyView {...readOnlyDefaults} />)

    const input = screen.getByPlaceholderText('Filter by keyword')
    await user.type(input, 'zzz-nonexistent')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('No results found')).toBeInTheDocument()
    })
  })

  it('restores the table when Clear all filters is used from EmptyStateFilter', async () => {
    const user = userEvent.setup()
    render(<ReadOnlyView {...readOnlyDefaults} />)

    const input = screen.getByPlaceholderText('Filter by keyword')
    await user.type(input, 'zzz-nonexistent')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('No results found')).toBeInTheDocument()
    })

    const clearButtons = screen.getAllByRole('button', { name: /clear all filters/i })
    await user.click(clearButtons[clearButtons.length - 1])

    await waitFor(() => {
      expect(screen.getByText('idp-admin')).toBeInTheDocument()
      expect(screen.queryByText('No results found')).not.toBeInTheDocument()
    })
  })

  it('paginates client-side when there are more than 20 mappings', async () => {
    const user = userEvent.setup()
    const manyEntries: GroupMappingEntry[] = Array.from({ length: 21 }, (_, i) => ({
      key: `km${i}`,
      idpGroupValue: `idp-row-${i}`,
      mappedGroupId: 'g1',
    }))

    render(<ReadOnlyView {...readOnlyDefaults} entries={manyEntries} />)

    expect(screen.getByText('idp-row-0')).toBeInTheDocument()
    expect(screen.getByText('idp-row-19')).toBeInTheDocument()
    expect(screen.queryByText('idp-row-20')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Go to next page' }))

    await waitFor(() => {
      expect(screen.queryByText('idp-row-0')).not.toBeInTheDocument()
      expect(screen.getByText('idp-row-20')).toBeInTheDocument()
    })
  })
})
