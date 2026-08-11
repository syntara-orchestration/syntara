import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { IdpGroupValueInput, MappingRow, NexusGroupMappingSelect } from './groupMappingFields'
import type { GroupMappingEntry, NexusGroup } from './groupMappingUtils'

const mockNexusGroups: NexusGroup[] = [
  { id: 'g1', name: 'admin', description: 'Administrators' },
  { id: 'g2', name: 'users', description: 'Regular users' },
  { id: 'g3', name: 'developers', description: 'Development team' },
]

describe('IdpGroupValueInput', () => {
  const defaultProps = {
    index: 0,
    value: '',
    onChange: vi.fn(),
  }

  it('renders text input with placeholder', () => {
    render(<IdpGroupValueInput {...defaultProps} />)

    expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('IdP group value')).toBeInTheDocument()
  })

  it('displays current value', () => {
    render(<IdpGroupValueInput {...defaultProps} value="admin-users" />)

    expect(screen.getByRole('textbox')).toHaveValue('admin-users')
  })

  it('calls onChange when value is typed', async () => {
    const user = userEvent.setup()
    function ControlledHarness() {
      const [value, setValue] = useState('')
      return <IdpGroupValueInput {...defaultProps} value={value} onChange={setValue} />
    }
    render(<ControlledHarness />)

    const input = screen.getByRole('textbox')
    await user.type(input, 'test')

    expect(screen.getByRole('textbox')).toHaveValue('test')
  })

  it('is disabled when isReadOnly is true', () => {
    render(<IdpGroupValueInput {...defaultProps} isReadOnly />)

    expect(screen.getByRole('textbox')).toBeDisabled()
  })

  it('uses inputId when provided for FormGroup association', () => {
    render(<IdpGroupValueInput {...defaultProps} inputId="custom-id" />)

    const input = screen.getByRole('textbox')
    expect(input).toHaveAttribute('id', 'custom-id')
    // When inputId is provided, aria-label should be omitted (FormGroup provides labeling)
    expect(input).not.toHaveAttribute('aria-label')
  })

  it('uses aria-label when inputId is not provided', () => {
    render(<IdpGroupValueInput {...defaultProps} index={2} />)

    expect(screen.getByRole('textbox')).toHaveAttribute('aria-label', 'IdP group value 3')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<IdpGroupValueInput {...defaultProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('NexusGroupMappingSelect', () => {
  const defaultEntry: GroupMappingEntry = {
    key: 'k1',
    idpGroupValue: 'idp-admin',
    nexusGroupId: '',
  }

  const defaultProps = {
    entry: defaultEntry,
    nexusGroups: mockNexusGroups,
    onChange: vi.fn(),
    onCreateGroup: vi.fn(),
  }

  it('renders typeahead select with placeholder', () => {
    render(<NexusGroupMappingSelect {...defaultProps} />)

    expect(screen.getByPlaceholderText('Select a group...')).toBeInTheDocument()
  })

  it('displays selected group name', () => {
    const entry = { ...defaultEntry, nexusGroupId: 'g1' }
    render(<NexusGroupMappingSelect {...defaultProps} entry={entry} />)

    expect(screen.getByDisplayValue('admin')).toBeInTheDocument()
  })

  it('opens dropdown when clicked', async () => {
    const user = userEvent.setup()
    render(<NexusGroupMappingSelect {...defaultProps} />)

    await user.click(screen.getByPlaceholderText('Select a group...'))

    expect(screen.getByRole('option', { name: /admin/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /users/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /developers/i })).toBeInTheDocument()
  })

  it('filters groups by name when typing', async () => {
    const user = userEvent.setup()
    render(<NexusGroupMappingSelect {...defaultProps} />)

    await user.click(screen.getByPlaceholderText('Select a group...'))
    await user.type(screen.getByPlaceholderText('Select a group...'), 'dev')

    expect(screen.getByRole('option', { name: /developers/i })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /admin/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /users/i })).not.toBeInTheDocument()
  })

  it('shows "no match" message when filter has no results', async () => {
    const user = userEvent.setup()
    render(<NexusGroupMappingSelect {...defaultProps} />)

    await user.click(screen.getByPlaceholderText('Select a group...'))
    await user.type(screen.getByPlaceholderText('Select a group...'), 'zzz-no-match')

    expect(screen.getByText(/No groups match "zzz-no-match"/i)).toBeInTheDocument()
  })

  it('calls onChange when a group is selected', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<NexusGroupMappingSelect {...defaultProps} onChange={onChange} />)

    await user.click(screen.getByPlaceholderText('Select a group...'))
    await user.click(screen.getByRole('option', { name: /admin/i }))

    expect(onChange).toHaveBeenCalledWith({ ...defaultEntry, nexusGroupId: 'g1' })
  })

  it('displays "Create new group" option', async () => {
    const user = userEvent.setup()
    render(<NexusGroupMappingSelect {...defaultProps} />)

    await user.click(screen.getByPlaceholderText('Select a group...'))

    expect(screen.getByRole('option', { name: /create new group/i })).toBeInTheDocument()
  })

  it('calls onCreateGroup when "Create new group" is clicked', async () => {
    const onCreateGroup = vi.fn()
    const user = userEvent.setup()
    render(<NexusGroupMappingSelect {...defaultProps} onCreateGroup={onCreateGroup} />)

    await user.click(screen.getByPlaceholderText('Select a group...'))
    await user.click(screen.getByRole('option', { name: /create new group/i }))

    expect(onCreateGroup).toHaveBeenCalledOnce()
  })

  it('shows danger status when validation fails', () => {
    const entry = { ...defaultEntry, idpGroupValue: 'admin' } // has IdP value but no Nexus group
    render(<NexusGroupMappingSelect {...defaultProps} entry={entry} showValidation />)

    const filterInput = screen.getByPlaceholderText('Select a group...')
    // Traverse to our wrapper (data-group-mapping-invalid), not PatternFly layout classes
    // eslint-disable-next-line testing-library/no-node-access
    expect(filterInput.closest('[data-group-mapping-invalid]')).toHaveAttribute('data-group-mapping-invalid', 'true')
  })

  it('is disabled when isReadOnly is true', () => {
    render(<NexusGroupMappingSelect {...defaultProps} isReadOnly />)

    expect(screen.getByPlaceholderText('Select a group...')).toBeDisabled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<NexusGroupMappingSelect {...defaultProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when open', async () => {
    const user = userEvent.setup()
    const { container } = render(<NexusGroupMappingSelect {...defaultProps} />)

    await user.click(screen.getByPlaceholderText('Select a group...'))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('MappingRow', () => {
  const defaultEntry: GroupMappingEntry = {
    key: 'k1',
    idpGroupValue: 'idp-admin',
    nexusGroupId: 'g1',
  }

  const defaultProps = {
    entry: defaultEntry,
    index: 0,
    nexusGroups: mockNexusGroups,
    onIdpGroupValueChange: vi.fn(),
    onNexusGroupIdChange: vi.fn(),
    onRemove: vi.fn(),
    onCreateGroup: vi.fn(),
  }

  describe('Editable mode', () => {
    it('renders both input controls', () => {
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} />
          </tbody>
        </table>
      )

      expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeInTheDocument()
      expect(screen.getByDisplayValue('admin')).toBeInTheDocument()
    })

    it('shows remove button', () => {
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} />
          </tbody>
        </table>
      )

      expect(screen.getByRole('button', { name: 'Remove mapping 1' })).toBeInTheDocument()
    })

    it('calls onChange when IdP value changes', async () => {
      const user = userEvent.setup()
      const initialEntry = { ...defaultEntry, idpGroupValue: '' }
      function ControlledMappingRowHarness() {
        const [entry, setEntry] = useState<GroupMappingEntry>(initialEntry)
        return (
          <table>
            <tbody>
              <MappingRow
                {...defaultProps}
                entry={entry}
                onIdpGroupValueChange={(_index, value) => setEntry((prev) => ({ ...prev, idpGroupValue: value }))}
                onNexusGroupIdChange={(_index, nexusGroupId) => setEntry((prev) => ({ ...prev, nexusGroupId }))}
              />
            </tbody>
          </table>
        )
      }
      render(<ControlledMappingRowHarness />)

      const input = screen.getByRole('textbox', { name: 'IdP group value 1' })
      await user.type(input, 'new-value')

      expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toHaveValue('new-value')
    })

    it('calls onRemove when remove button is clicked', async () => {
      const onRemove = vi.fn()
      const user = userEvent.setup()
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} onRemove={onRemove} />
          </tbody>
        </table>
      )

      await user.click(screen.getByRole('button', { name: 'Remove mapping 1' }))

      expect(onRemove).toHaveBeenCalledWith(0)
    })

    it('has no accessibility violations', async () => {
      const { container } = render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} />
          </tbody>
        </table>
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Read-only mode with disabled inputs', () => {
    it('renders disabled inputs', () => {
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} isReadOnly />
          </tbody>
        </table>
      )

      expect(screen.getByRole('textbox', { name: 'IdP group value 1' })).toBeDisabled()
      expect(screen.getByDisplayValue('admin')).toBeDisabled()
    })

    it('hides remove button by default', () => {
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} isReadOnly />
          </tbody>
        </table>
      )

      expect(screen.queryByRole('button', { name: 'Remove mapping 1' })).not.toBeInTheDocument()
    })

    it('has no accessibility violations', async () => {
      const { container } = render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} isReadOnly />
          </tbody>
        </table>
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Read-only mode with plain cells', () => {
    it('renders plain text content instead of inputs', () => {
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} isReadOnly readOnlyPlainCells />
          </tbody>
        </table>
      )

      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      expect(screen.getByText('idp-admin')).toBeInTheDocument()
      expect(screen.getByText('admin')).toBeInTheDocument()
    })

    it('links Nexus group names to group detail pages', () => {
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} isReadOnly readOnlyPlainCells />
          </tbody>
        </table>
      )

      expect(screen.getByRole('link', { name: 'admin' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/groups/g1'
      )
    })

    it('shows remove button when readOnlyAllowRemove is true', () => {
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} isReadOnly readOnlyPlainCells readOnlyAllowRemove />
          </tbody>
        </table>
      )

      expect(screen.getByRole('button', { name: 'Remove mapping 1' })).toBeInTheDocument()
    })

    it('calls onRemove when remove button is clicked', async () => {
      const onRemove = vi.fn()
      const user = userEvent.setup()
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} isReadOnly readOnlyPlainCells readOnlyAllowRemove onRemove={onRemove} />
          </tbody>
        </table>
      )

      await user.click(screen.getByRole('button', { name: 'Remove mapping 1' }))

      expect(onRemove).toHaveBeenCalledWith(0)
    })

    it('displays em dash for empty values', () => {
      const emptyEntry: GroupMappingEntry = { key: 'k2', idpGroupValue: '', nexusGroupId: '' }
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} entry={emptyEntry} isReadOnly readOnlyPlainCells />
          </tbody>
        </table>
      )

      const cells = screen.getAllByText('—')
      expect(cells).toHaveLength(2) // Both IdP value and group should show em dash
    })

    it('has no accessibility violations', async () => {
      const { container } = render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} isReadOnly readOnlyPlainCells readOnlyAllowRemove />
          </tbody>
        </table>
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Validation states', () => {
    it('shows validation error when IdP has value but no Nexus group', () => {
      const incompleteEntry = { ...defaultEntry, nexusGroupId: '' }
      render(
        <table>
          <tbody>
            <MappingRow {...defaultProps} entry={incompleteEntry} showValidation />
          </tbody>
        </table>
      )

      const filterInput = screen.getByPlaceholderText('Select a group...')
      // eslint-disable-next-line testing-library/no-node-access
      expect(filterInput.closest('[data-group-mapping-invalid]')).toHaveAttribute('data-group-mapping-invalid', 'true')
    })
  })
})
