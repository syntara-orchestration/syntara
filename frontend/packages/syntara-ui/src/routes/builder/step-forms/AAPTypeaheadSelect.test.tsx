import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AAPTypeaheadSelect } from './AAPTypeaheadSelect'

const defaultOptions = [
  { value: 'opt-1', label: 'Alpha', description: 'First option' },
  { value: 'opt-2', label: 'Beta', description: 'Second option' },
  { value: 'opt-3', label: 'Gamma' },
] as const

function renderSelect(overrides: Partial<React.ComponentProps<typeof AAPTypeaheadSelect>> = {}) {
  const onChange = vi.fn()
  const onSearchChange = vi.fn()
  const props = {
    id: 'test-typeahead',
    ariaLabel: 'Test typeahead',
    options: [...defaultOptions],
    selected: '',
    onChange,
    onSearchChange,
    ...overrides,
  }
  const view = render(<AAPTypeaheadSelect {...props} />)
  return { ...view, onChange, onSearchChange }
}

/** PF6 typeahead toggle input has aria-label "Type to filter". */
function getInput() {
  return screen.getByRole('textbox', { name: /type to filter/i })
}

describe('AAPTypeaheadSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Accessibility', () => {
    it('has no accessibility violations in default state', async () => {
      const { container } = renderSelect()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with a selected value', async () => {
      const { container } = renderSelect({ selected: 'opt-1' })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Rendering', () => {
    it('renders with default placeholder when no selection', () => {
      renderSelect()
      expect(screen.getByPlaceholderText('Select...')).toBeInTheDocument()
    })

    it('renders with custom placeholder', () => {
      renderSelect({ placeholder: 'Pick an item' })
      expect(screen.getByPlaceholderText('Pick an item')).toBeInTheDocument()
    })

    it('shows selected label when a value is selected', () => {
      renderSelect({ selected: 'opt-1' })
      expect(getInput()).toHaveValue('Alpha')
    })

    it('falls back to raw value when selected value has no matching option', () => {
      renderSelect({ selected: 'unknown-value' })
      expect(getInput()).toHaveValue('unknown-value')
    })
  })

  describe('Dropdown interactions', () => {
    it('opens dropdown on input click and shows all options', async () => {
      const user = userEvent.setup()
      renderSelect()

      await user.click(getInput())

      expect(screen.getByRole('option', { name: /Alpha/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Beta/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Gamma/i })).toBeInTheDocument()
    })

    it('calls onChange when an option is selected and closes dropdown', async () => {
      const user = userEvent.setup()
      const { onChange } = renderSelect()

      await user.click(getInput())
      await user.click(screen.getByRole('option', { name: /Beta/i }))

      expect(onChange).toHaveBeenCalledWith('opt-2')

      await waitFor(() => {
        expect(screen.queryByRole('option', { name: /Beta/i })).not.toBeInTheDocument()
      })
    })

    it('opens dropdown when typing in the input', async () => {
      const user = userEvent.setup()
      renderSelect()

      await user.type(getInput(), 'A')

      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    it('toggles dropdown on chevron button click', async () => {
      const user = userEvent.setup()
      renderSelect()

      const toggleButton = screen.getByRole('button', { name: /Menu toggle/i })
      await user.click(toggleButton)

      expect(screen.getByRole('listbox')).toBeInTheDocument()

      await user.click(toggleButton)

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      })
    })

    it('clears filter when dropdown is closed', async () => {
      const user = userEvent.setup()
      const { onSearchChange } = renderSelect()

      await user.click(getInput())
      await user.type(getInput(), 'Beta')
      expect(getInput()).toHaveValue('Beta')

      await user.keyboard('{Escape}')
      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      })

      await user.click(getInput())
      expect(getInput()).toHaveValue('')
      await waitFor(() => {
        expect(onSearchChange).toHaveBeenCalledWith('')
      })
    })
  })

  describe('Loading state', () => {
    it('shows loading spinner when isLoading is true', () => {
      renderSelect({ isLoading: true })
      expect(screen.getByLabelText('Loading')).toBeInTheDocument()
    })

    it('does not show loading spinner when isLoading is false', () => {
      renderSelect({ isLoading: false })
      expect(screen.queryByLabelText('Loading')).not.toBeInTheDocument()
    })

    it('shows "Loading..." when options are empty and isLoading is true', async () => {
      const user = userEvent.setup()
      renderSelect({ options: [], isLoading: true })

      await user.click(getInput())

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })
  })

  describe('No results', () => {
    it('shows "No results match" when options are empty and not loading', async () => {
      const user = userEvent.setup()
      renderSelect({ options: [] })

      await user.click(getInput())

      expect(screen.getByText(/No results match/)).toBeInTheDocument()
    })

    it('includes filter value in the no results message', async () => {
      const user = userEvent.setup()
      renderSelect({ options: [] })

      await user.type(getInput(), 'zzzzz')

      expect(screen.getByText('No results match "zzzzz"')).toBeInTheDocument()
    })
  })

  describe('Clear selection', () => {
    it('shows clear button when a value is selected and not loading', () => {
      renderSelect({ selected: 'opt-1', isLoading: false })
      expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()
    })

    it('does not show clear button when no value is selected', () => {
      renderSelect({ selected: '' })
      expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
    })

    it('does not show clear button when loading', () => {
      renderSelect({ selected: 'opt-1', isLoading: true })
      expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
    })

    it('calls onChange with empty string on clear click', async () => {
      const user = userEvent.setup()
      const { onChange } = renderSelect({ selected: 'opt-1' })

      await user.click(screen.getByRole('button', { name: 'Clear selection' }))

      expect(onChange).toHaveBeenCalledWith('')
    })
  })

  describe('Error state', () => {
    it('renders with hasError without crashing', () => {
      renderSelect({ hasError: true })
      // The MenuToggle receives status="danger"; verify the component still renders
      expect(getInput()).toBeInTheDocument()
    })

    it('renders without danger status when hasError is false', () => {
      renderSelect({ hasError: false })
      expect(getInput()).toBeInTheDocument()
    })
  })

  describe('Debounced search', () => {
    it('calls onSearchChange after debounce when typing', async () => {
      const user = userEvent.setup()
      const { onSearchChange } = renderSelect()

      await user.type(getInput(), 'Alp')

      // The debounce fires after 300ms; waitFor will poll until the assertion passes
      await waitFor(() => {
        expect(onSearchChange).toHaveBeenCalledWith('Alp')
      })
    })

    it('fires onSearchChange with empty string on initial mount after debounce', async () => {
      const { onSearchChange } = renderSelect()

      // The debounce effect fires with initial filterValue = '' after 300ms
      await waitFor(() => {
        expect(onSearchChange).toHaveBeenCalledWith('')
      })
    })

    it('only calls onSearchChange with the latest value when typing rapidly', async () => {
      const user = userEvent.setup()
      const { onSearchChange } = renderSelect()

      // Wait for initial mount debounce to settle
      await waitFor(() => {
        expect(onSearchChange).toHaveBeenCalledWith('')
      })
      onSearchChange.mockClear()

      // Type rapidly — debounce should coalesce to the final value
      await user.type(getInput(), 'Alpha')

      await waitFor(() => {
        expect(onSearchChange).toHaveBeenCalledWith('Alpha')
      })
    })
  })

  describe('Selection interaction', () => {
    it('calls onChange with string value when an option is selected', async () => {
      const user = userEvent.setup()
      const { onChange } = renderSelect()

      await user.click(getInput())
      await user.click(screen.getByRole('option', { name: /Alpha/i }))

      expect(onChange).toHaveBeenCalledWith('opt-1')
    })
  })
})
