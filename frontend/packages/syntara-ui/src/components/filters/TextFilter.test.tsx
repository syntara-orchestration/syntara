import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'

import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import { FilterTypeEnum } from '../../types/filters'

import { TextFilter } from './TextFilter'
import { SEARCH_THRESHOLD } from './textFilterSelectControls'

vi.mock('./DateRangeFilter', () => ({
  DateRangeFilter: (props: { fieldKey: string; label: string; onChange: (filters: FilterConfig[]) => void }) => (
    <div data-testid="date-range-filter">
      {props.label} date range
      <button
        type="button"
        data-testid="date-range-apply"
        onClick={() => props.onChange([{ key: props.fieldKey, operator: 'gte', value: '2025-01-01' }])}
      >
        Save range
      </button>
    </div>
  ),
}))

describe('TextFilter', () => {
  const textFieldDefinition: FilterFieldDefinition = {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    defaultOperator: 'contains',
    placeholder: 'Filter by name',
  }

  const selectFieldDefinition: FilterFieldDefinition = {
    key: 'status',
    label: 'Status',
    type: FilterTypeEnum.SELECT,
    options: [
      { label: 'Enabled', value: 'true' },
      { label: 'Disabled', value: 'false' },
    ],
    placeholder: 'Filter by status',
  }

  const defaultProps = {
    fieldDefinitions: [textFieldDefinition, selectFieldDefinition],
    filters: [],
    onFilterChange: vi.fn(),
  }

  describe('field selector', () => {
    it('renders field selector with first field selected by default', () => {
      render(<TextFilter {...defaultProps} />)

      expect(screen.getByText('Name')).toBeInTheDocument()
    })

    it('allows switching between fields', async () => {
      const user = userEvent.setup()
      render(<TextFilter {...defaultProps} />)

      // Click field selector
      const fieldSelector = screen.getByText('Name')
      await user.click(fieldSelector)

      // Select Status field
      const statusOption = screen.getByText('Status')
      await user.click(statusOption)

      // Field selector should now show Status
      expect(screen.getByText('Filter by status')).toBeInTheDocument()
    })
  })

  describe('text field filtering', () => {
    it('renders text input for TEXT field type', () => {
      render(<TextFilter {...defaultProps} />)

      expect(screen.getByPlaceholderText('Filter by name')).toBeInTheDocument()
    })

    it('applies filter when arrow button is clicked', async () => {
      const user = userEvent.setup()
      const onFilterChange = vi.fn()

      render(<TextFilter {...defaultProps} onFilterChange={onFilterChange} />)

      const input = screen.getByPlaceholderText('Filter by name')
      await user.type(input, 'test')

      // Filter should not be applied yet
      expect(onFilterChange).not.toHaveBeenCalled()

      // Click the arrow button
      const applyButton = screen.getByLabelText('Apply filter')
      await user.click(applyButton)

      expect(onFilterChange).toHaveBeenCalledWith({
        key: 'name',
        operator: 'contains',
        value: 'test',
      })
    })

    it('applies filter on Enter key', async () => {
      const user = userEvent.setup()
      const onFilterChange = vi.fn()

      render(<TextFilter {...defaultProps} onFilterChange={onFilterChange} />)

      const input = screen.getByPlaceholderText('Filter by name')
      await user.type(input, 'test{Enter}')

      expect(onFilterChange).toHaveBeenCalledWith({
        key: 'name',
        operator: 'contains',
        value: 'test',
      })
    })

    it('displays active filter value in input', () => {
      const filters = [{ key: 'name', operator: 'contains' as const, value: 'existing-filter' }]

      render(<TextFilter {...defaultProps} filters={filters} />)

      expect(screen.getByDisplayValue('existing-filter')).toBeInTheDocument()
    })

    it('allows editing active filter value', async () => {
      const user = userEvent.setup()
      const onFilterChange = vi.fn()
      const filters = [{ key: 'name', operator: 'contains' as const, value: 'original' }]

      render(<TextFilter {...defaultProps} filters={filters} onFilterChange={onFilterChange} />)

      const input = screen.getByDisplayValue('original')
      await user.clear(input)
      await user.type(input, 'modified{Enter}')

      expect(onFilterChange).toHaveBeenCalledWith({
        key: 'name',
        operator: 'contains',
        value: 'modified',
      })
    })

    it('clears filter when input is emptied and Enter pressed', async () => {
      const user = userEvent.setup()
      const onFilterChange = vi.fn()
      const filters = [{ key: 'name', operator: 'contains' as const, value: 'test' }]

      render(<TextFilter {...defaultProps} filters={filters} onFilterChange={onFilterChange} />)

      const input = screen.getByDisplayValue('test')
      await user.clear(input)
      await user.type(input, '{Enter}')

      expect(onFilterChange).toHaveBeenCalledWith(null, 'name')
    })
  })

  describe('select field filtering', () => {
    it('renders select dropdown for SELECT field type', () => {
      const fieldDefinitions = [selectFieldDefinition]

      render(<TextFilter {...defaultProps} fieldDefinitions={fieldDefinitions} />)

      // Field selector shows Status
      expect(screen.getByText('Status')).toBeInTheDocument()
      // Value selector shows placeholder
      expect(screen.getByText('Filter by status')).toBeInTheDocument()
    })

    it('applies filter when option is selected', async () => {
      const user = userEvent.setup()
      const onFilterChange = vi.fn()
      const fieldDefinitions = [selectFieldDefinition]

      render(<TextFilter {...defaultProps} fieldDefinitions={fieldDefinitions} onFilterChange={onFilterChange} />)

      // Click value selector
      const valueSelector = screen.getByText('Filter by status')
      await user.click(valueSelector)

      // Select an option
      const enabledOption = screen.getByText('Enabled')
      await user.click(enabledOption)

      expect(onFilterChange).toHaveBeenCalledWith({
        key: 'status',
        operator: 'eq',
        value: 'true',
      })
    })

    it('displays active filter value in selector', () => {
      const fieldDefinitions = [selectFieldDefinition]
      const filters = [{ key: 'status', operator: 'eq' as const, value: 'true' }]

      render(<TextFilter {...defaultProps} fieldDefinitions={fieldDefinitions} filters={filters} />)

      // Value selector should show the selected option label
      expect(screen.getByText('Enabled')).toBeInTheDocument()
    })
  })

  describe('field switching behavior', () => {
    it('clears input when switching fields', async () => {
      const user = userEvent.setup()

      render(<TextFilter {...defaultProps} />)

      // Type into Name field
      const input = screen.getByPlaceholderText('Filter by name')
      await user.type(input, 'test')

      // Switch to Status field
      const fieldSelector = screen.getByText('Name')
      await user.click(fieldSelector)
      const statusOption = screen.getByText('Status')
      await user.click(statusOption)

      // Should show status selector, not the typed text
      expect(screen.getByText('Filter by status')).toBeInTheDocument()
      expect(screen.queryByDisplayValue('test')).not.toBeInTheDocument()
    })

    it('selects field based on last filter in filters array', () => {
      // With status filter as the last filter
      const filters = [
        { key: 'name', operator: 'contains' as const, value: 'test' },
        { key: 'status', operator: 'eq' as const, value: 'true' },
      ]

      render(<TextFilter {...defaultProps} filters={filters} />)

      // Should select Status field (last filter); value toggle shows "Enabled" for this fixture
      expect(screen.getByRole('button', { name: 'Status' })).toBeInTheDocument()
    })

    it('defaults to first field when no filters present', () => {
      render(<TextFilter {...defaultProps} filters={[]} />)

      // Should default to Name (first field)
      expect(screen.getByText('Name')).toBeInTheDocument()
    })
  })

  describe('multiselect filter', () => {
    const multiselectFieldDefinition: FilterFieldDefinition = {
      key: 'tags',
      label: 'Tags',
      type: FilterTypeEnum.MULTISELECT,
      options: [
        { label: 'Production', value: 'prod' },
        { label: 'Staging', value: 'staging' },
        { label: 'Development', value: 'dev' },
      ],
      placeholder: 'Select tags',
    }

    const multiselectProps = {
      fieldDefinitions: [multiselectFieldDefinition],
      filters: [],
      onFilterChange: vi.fn(),
    }

    it('renders multiselect toggle with placeholder', () => {
      render(<TextFilter {...multiselectProps} />)
      expect(screen.getByText('Select tags')).toBeInTheDocument()
    })

    it('shows options when multiselect is opened', async () => {
      const user = userEvent.setup()
      render(<TextFilter {...multiselectProps} />)

      await user.click(screen.getByText('Select tags'))

      expect(screen.getByText('Production')).toBeInTheDocument()
      expect(screen.getByText('Staging')).toBeInTheDocument()
      expect(screen.getByText('Development')).toBeInTheDocument()
    })

    it('selects an option from multiselect', async () => {
      const user = userEvent.setup()
      const onFilterChange = vi.fn()
      render(<TextFilter {...multiselectProps} onFilterChange={onFilterChange} />)

      await user.click(screen.getByText('Select tags'))
      await user.click(screen.getByText('Production'))

      expect(onFilterChange).toHaveBeenCalledTimes(1)
    })

    it('shows selected count when filters are present', () => {
      const filters = [{ key: 'tags', operator: 'in' as const, value: ['prod'] }]
      render(<TextFilter {...multiselectProps} filters={filters} />)

      expect(screen.getByText('1 selected')).toBeInTheDocument()
    })
  })

  describe('select filter close behavior', () => {
    it('clears search when select is closed', async () => {
      const user = userEvent.setup()
      render(<TextFilter {...defaultProps} />)

      const fieldSelector = screen.getByText('Name')
      await user.click(fieldSelector)
      await user.click(screen.getByText('Status'))

      const statusToggle = screen.getByText('Filter by status')
      await user.click(statusToggle)
      expect(screen.getByText('Enabled')).toBeInTheDocument()

      await user.click(statusToggle)

      await waitFor(() => {
        expect(screen.queryByText('Enabled')).not.toBeInTheDocument()
      })
    })
  })

  describe('date range field', () => {
    const dateRangeField: FilterFieldDefinition = {
      key: 'created',
      label: 'Created',
      type: FilterTypeEnum.DATERANGE,
    }

    it('renders date range control and forwards range changes', async () => {
      const user = userEvent.setup()
      const onDateRangeChange = vi.fn()

      render(
        <TextFilter
          fieldDefinitions={[dateRangeField]}
          filters={[]}
          onFilterChange={vi.fn()}
          onDateRangeChange={onDateRangeChange}
        />
      )

      expect(screen.getByTestId('date-range-filter')).toBeInTheDocument()
      expect(screen.getByText(/Created date range/i)).toBeInTheDocument()

      await user.click(screen.getByTestId('date-range-apply'))

      expect(onDateRangeChange).toHaveBeenCalledWith(
        'created',
        expect.arrayContaining([expect.objectContaining({ key: 'created', operator: 'gte', value: '2025-01-01' })])
      )
    })

    it('passes gte and lte filter values into the date range control', () => {
      const filters: FilterConfig[] = [
        { key: 'created', operator: 'gte', value: '2024-06-01' },
        { key: 'created', operator: 'lte', value: '2024-06-30' },
      ]

      render(
        <TextFilter
          fieldDefinitions={[dateRangeField]}
          filters={filters}
          onFilterChange={vi.fn()}
          onDateRangeChange={vi.fn()}
        />
      )

      expect(screen.getByTestId('date-range-filter')).toBeInTheDocument()
    })

    it('does not throw when date range changes without onDateRangeChange', async () => {
      const user = userEvent.setup()

      render(<TextFilter fieldDefinitions={[dateRangeField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByTestId('date-range-apply'))

      expect(screen.getByTestId('date-range-filter')).toBeInTheDocument()
    })
  })

  describe('async select field', () => {
    it('shows getOptionLabel for a preloaded value before async options resolve', () => {
      const asyncField: FilterFieldDefinition = {
        key: 'workflow_id',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: () => new Promise<{ label: string; value: string }[]>(() => {}),
        getOptionLabel: (value) => (value === 'stored-1' ? 'Stored workflow' : undefined),
      }
      const filters = [{ key: 'workflow_id', operator: 'eq' as const, value: 'stored-1' }]

      render(<TextFilter fieldDefinitions={[asyncField]} filters={filters} onFilterChange={vi.fn()} />)

      expect(screen.getByText('Stored workflow')).toBeInTheDocument()
    })

    it('shows loading then options when async list resolves', async () => {
      const user = userEvent.setup()
      let resolveLoad!: (rows: { label: string; value: string }[]) => void
      const asyncField: FilterFieldDefinition = {
        key: 'wf',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: () =>
          new Promise<{ label: string; value: string }[]>((resolve) => {
            resolveLoad = resolve
          }),
      }

      render(<TextFilter fieldDefinitions={[asyncField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by workflow'))

      expect(await screen.findByText('Loading...')).toBeInTheDocument()

      resolveLoad([{ label: 'Option A', value: 'a' }])

      expect(await screen.findByText('Option A')).toBeInTheDocument()
    })

    it('calls onOptionSelected when an async option is chosen', async () => {
      const user = userEvent.setup()
      const onOptionSelected = vi.fn()
      const asyncField: FilterFieldDefinition = {
        key: 'wf',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: () => Promise.resolve([{ label: 'Alpha', value: 'alpha' }]),
        onOptionSelected,
      }

      render(<TextFilter fieldDefinitions={[asyncField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by workflow'))
      await user.click(await screen.findByText('Alpha'))

      expect(onOptionSelected).toHaveBeenCalledWith('alpha', 'Alpha')
    })

    it('clears async search and reloads when search clear is used', async () => {
      const user = userEvent.setup()
      const asyncField: FilterFieldDefinition = {
        key: 'wf',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: () => Promise.resolve([{ label: 'Alpha', value: 'alpha' }]),
      }

      render(<TextFilter fieldDefinitions={[asyncField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by workflow'))
      await screen.findByText('Alpha')

      const search = screen.getByPlaceholderText('Search...')
      await user.type(search, 'alp')

      await user.click(screen.getByRole('button', { name: 'Reset' }))

      expect(await screen.findByText('Alpha')).toBeInTheDocument()
    })

    it('invalidates async work when the value menu closes', async () => {
      const user = userEvent.setup()
      let resolveLoad!: (rows: { label: string; value: string }[]) => void
      const asyncField: FilterFieldDefinition = {
        key: 'wf',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: () =>
          new Promise<{ label: string; value: string }[]>((resolve) => {
            resolveLoad = resolve
          }),
      }

      render(<TextFilter fieldDefinitions={[asyncField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by workflow'))
      expect(await screen.findByText('Loading...')).toBeInTheDocument()

      await user.click(screen.getByText('Filter by workflow'))

      resolveLoad([{ label: 'Stale', value: 'stale' }])

      await waitFor(() => {
        expect(screen.queryByText('Stale')).not.toBeInTheDocument()
      })
    })

    it('clears pending async search debounce when the value menu closes', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
      const asyncOptionsFn = vi.fn((search: string) => {
        if (search === '') {
          return Promise.resolve([{ label: 'Alpha', value: 'alpha' }])
        }
        return Promise.resolve([{ label: `Result for ${search}`, value: search }])
      })
      const asyncField: FilterFieldDefinition = {
        key: 'wf',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: asyncOptionsFn,
      }

      render(<TextFilter fieldDefinitions={[asyncField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by workflow'))
      expect(await screen.findByText('Alpha')).toBeInTheDocument()

      const callsAfterOpen = asyncOptionsFn.mock.calls.length

      await user.type(screen.getByPlaceholderText('Search...'), 'be')
      await user.click(screen.getByText('Filter by workflow'))

      vi.advanceTimersByTime(300)

      expect(asyncOptionsFn.mock.calls.length).toBe(callsAfterOpen)
      expect(screen.queryByText('Result for be')).not.toBeInTheDocument()

      vi.useRealTimers()
    })

    it('shows empty list when async options request fails', async () => {
      const user = userEvent.setup()
      const asyncField: FilterFieldDefinition = {
        key: 'wf',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: () => Promise.reject(new Error('network error')),
      }

      render(<TextFilter fieldDefinitions={[asyncField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by workflow'))

      expect(await screen.findByText('No results found')).toBeInTheDocument()
    })

    it('keeps the selected async option label when search results no longer include it', async () => {
      const user = userEvent.setup()
      const asyncOptionsFn = vi.fn((search: string) => {
        if (search === 'z') {
          return Promise.resolve([])
        }
        return Promise.resolve([
          { label: 'Alpha workflow', value: 'alpha' },
          { label: 'Beta workflow', value: 'beta' },
        ])
      })
      const asyncField: FilterFieldDefinition = {
        key: 'wf',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: asyncOptionsFn,
      }

      function ControlledAsyncTextFilter() {
        const [filters, setFilters] = useState<FilterConfig[]>([])

        return (
          <TextFilter
            fieldDefinitions={[asyncField]}
            filters={filters}
            onFilterChange={(filter) => {
              setFilters(filter ? [filter] : [])
            }}
          />
        )
      }

      render(<ControlledAsyncTextFilter />)

      await user.click(screen.getByText('Filter by workflow'))
      await user.click(await screen.findByRole('option', { name: 'Alpha workflow' }))

      // Use role query to target only the toggle button — not the still-closing menu item
      // (PatternFly keeps the menu in the DOM during its CSS close transition)
      const selectedToggle = await screen.findByRole('button', { name: 'Alpha workflow' })
      await waitFor(() => {
        expect(screen.queryByRole('option', { name: 'Alpha workflow' })).not.toBeInTheDocument()
      })
      expect(selectedToggle).toBeInTheDocument()

      await user.click(selectedToggle)
      await user.type(screen.getByPlaceholderText('Search...'), 'z')

      expect(await screen.findByText('No results found')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Alpha workflow' })).toBeInTheDocument()
    })
  })

  describe('select search', () => {
    it('shows no results when client search matches nothing', async () => {
      const user = userEvent.setup()
      const manyOptionsField: FilterFieldDefinition = {
        key: 'category',
        label: 'Category',
        type: FilterTypeEnum.SELECT,
        options: Array.from({ length: SEARCH_THRESHOLD }, (_, i) => ({
          label: `Category ${i + 1}`,
          value: String(i + 1),
        })),
        placeholder: 'Filter by category',
      }

      render(<TextFilter fieldDefinitions={[manyOptionsField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by category'))
      await user.type(screen.getByPlaceholderText('Search...'), 'nomatchzzzz')

      expect(await screen.findByText('No results found')).toBeInTheDocument()
    })
  })

  describe('compact layout', () => {
    it('renders when isCompact is true', () => {
      render(<TextFilter {...defaultProps} isCompact />)
      expect(screen.getByText('Name')).toBeInTheDocument()
    })
  })

  describe('select menu constraints', () => {
    it('opens a scrollable value select with many options', async () => {
      const user = userEvent.setup()
      const manyOptionsField: FilterFieldDefinition = {
        key: 'category',
        label: 'Category',
        type: FilterTypeEnum.SELECT,
        options: Array.from({ length: SEARCH_THRESHOLD }, (_, i) => ({
          label: `Category ${i + 1}`,
          value: String(i + 1),
        })),
        placeholder: 'Filter by category',
      }

      render(<TextFilter fieldDefinitions={[manyOptionsField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by category'))

      expect(screen.getByRole('listbox')).toBeInTheDocument()
      expect(screen.getByText('Category 1')).toBeInTheDocument()
      expect(screen.getByText(`Category ${SEARCH_THRESHOLD}`)).toBeInTheDocument()
    })

    it('opens the value select in compact mode', async () => {
      const user = userEvent.setup()
      const selectOnlyProps = {
        fieldDefinitions: [selectFieldDefinition],
        filters: [] as FilterConfig[],
        onFilterChange: vi.fn(),
        isCompact: true,
      }

      render(<TextFilter {...selectOnlyProps} />)

      await user.click(screen.getByText('Filter by status'))

      expect(screen.getByRole('listbox')).toBeInTheDocument()
      expect(screen.getByText('Enabled')).toBeInTheDocument()
      expect(screen.getByText('Disabled')).toBeInTheDocument()
    })
  })

  describe('select search threshold', () => {
    it('hides search input when static options are fewer than the threshold', async () => {
      const user = userEvent.setup()
      const fewOptionsField: FilterFieldDefinition = {
        key: 'status',
        label: 'Status',
        type: FilterTypeEnum.SELECT,
        options: [
          { label: 'Enabled', value: 'true' },
          { label: 'Disabled', value: 'false' },
        ],
        placeholder: 'Filter by status',
      }

      render(<TextFilter fieldDefinitions={[fewOptionsField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by status'))

      expect(screen.getByText('Enabled')).toBeInTheDocument()
      expect(screen.getByText('Disabled')).toBeInTheDocument()
      expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument()
    })

    it('shows search input when static options meet the threshold', async () => {
      const user = userEvent.setup()
      const manyOptions = Array.from({ length: SEARCH_THRESHOLD }, (_, i) => ({
        label: `Option ${i + 1}`,
        value: String(i + 1),
      }))
      const manyOptionsField: FilterFieldDefinition = {
        key: 'category',
        label: 'Category',
        type: FilterTypeEnum.SELECT,
        options: manyOptions,
        placeholder: 'Filter by category',
      }

      render(<TextFilter fieldDefinitions={[manyOptionsField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by category'))

      expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument()
    })

    it('always shows search input for async options', async () => {
      const user = userEvent.setup()
      const asyncField: FilterFieldDefinition = {
        key: 'workflow_id',
        label: 'Workflow',
        type: FilterTypeEnum.SELECT,
        asyncOptions: () => Promise.resolve([{ label: 'Only one', value: '1' }]),
      }

      render(<TextFilter fieldDefinitions={[asyncField]} filters={[]} onFilterChange={vi.fn()} />)

      await user.click(screen.getByText('Filter by workflow'))

      expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument()
    })
  })
})
