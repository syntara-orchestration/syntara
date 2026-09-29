import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { TypeaheadSelect, type TypeaheadOption } from './TypeaheadSelect'

const defaultOptions: TypeaheadOption[] = [
  { value: 'opt-1', label: 'Alpha Option' },
  { value: 'opt-2', label: 'Beta Option', description: 'Second item' },
  { value: 'opt-3', label: 'Gamma Option' },
]

function renderSelect(overrides: Partial<React.ComponentProps<typeof TypeaheadSelect>> = {}) {
  const props = {
    id: 'test-select',
    ariaLabel: 'Test select',
    options: defaultOptions,
    selected: '',
    onChange: vi.fn(),
    ...overrides,
  }
  const view = render(<TypeaheadSelect {...props} />)
  return { ...view, onChange: props.onChange }
}

/** The PF6 typeahead toggle input has aria-label "Type to filter". */
function getInput() {
  return screen.getByRole('textbox', { name: /type to filter/i })
}

describe('TypeaheadSelect', () => {
  describe('Accessibility', () => {
    it('places id on the input element for label association', () => {
      renderSelect({ id: 'can-i-resource-type' })
      expect(getInput()).toHaveAttribute('id', 'can-i-resource-type')
    })

    it('focuses input when associated label is clicked', async () => {
      const user = userEvent.setup()
      render(
        <>
          <label htmlFor="test-select">Resource type</label>
          <TypeaheadSelect
            id="test-select"
            ariaLabel="Resource type"
            options={defaultOptions}
            selected=""
            onChange={vi.fn()}
          />
        </>
      )

      await user.click(screen.getByText('Resource type'))
      expect(getInput()).toHaveFocus()
    })

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
    it('renders with placeholder text', () => {
      renderSelect({ placeholder: 'Pick one' })
      expect(screen.getByPlaceholderText('Pick one')).toBeInTheDocument()
    })

    it('renders default placeholder when none provided', () => {
      renderSelect()
      expect(screen.getByPlaceholderText('Select...')).toBeInTheDocument()
    })

    it('displays the selected option label in the input', () => {
      renderSelect({ selected: 'opt-1' })
      expect(getInput()).toHaveValue('Alpha Option')
    })

    it('shows clear button when a value is selected', () => {
      renderSelect({ selected: 'opt-2' })
      expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()
    })

    it('does not show clear button when no value is selected', () => {
      renderSelect({ selected: '' })
      expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
    })
  })

  describe('Dropdown interactions', () => {
    it('opens dropdown and shows all options when input is clicked', async () => {
      const user = userEvent.setup()
      renderSelect()

      await user.click(getInput())

      expect(screen.getByRole('option', { name: /Alpha Option/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Beta Option/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Gamma Option/i })).toBeInTheDocument()
    })

    it('calls onChange with the selected value when an option is clicked', async () => {
      const user = userEvent.setup()
      const { onChange } = renderSelect()

      await user.click(getInput())
      await user.click(screen.getByRole('option', { name: /Beta Option/i }))

      expect(onChange).toHaveBeenCalledWith('opt-2')
    })

    it('closes dropdown after selecting an option', async () => {
      const user = userEvent.setup()
      renderSelect()

      await user.click(getInput())
      expect(screen.getByRole('option', { name: /Alpha Option/i })).toBeInTheDocument()

      await user.click(screen.getByRole('option', { name: /Alpha Option/i }))

      await waitFor(() => {
        expect(screen.queryByRole('option', { name: /Alpha Option/i })).not.toBeInTheDocument()
      })
    })
  })

  describe('Filtering', () => {
    it('filters options based on text input', async () => {
      const user = userEvent.setup()
      renderSelect()

      await user.click(getInput())
      await user.type(getInput(), 'Beta')

      expect(screen.getByRole('option', { name: /Beta Option/i })).toBeInTheDocument()
      expect(screen.queryByRole('option', { name: /Alpha Option/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('option', { name: /Gamma Option/i })).not.toBeInTheDocument()
    })

    it('shows "No results match" when filter has no matches', async () => {
      const user = userEvent.setup()
      renderSelect()

      await user.click(getInput())
      await user.type(getInput(), 'zzzzz')

      expect(screen.getByText(/No results match/)).toBeInTheDocument()
    })

    it('filter is case-insensitive', async () => {
      const user = userEvent.setup()
      renderSelect()

      await user.click(getInput())
      await user.type(getInput(), 'alpha')

      expect(screen.getByRole('option', { name: /Alpha Option/i })).toBeInTheDocument()
    })

    it('clears filter when dropdown is closed', async () => {
      const user = userEvent.setup()
      renderSelect()

      await user.click(getInput())
      await user.type(getInput(), 'Beta')
      expect(screen.queryByRole('option', { name: /Alpha Option/i })).not.toBeInTheDocument()

      await user.keyboard('{Escape}')
      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      })

      await user.click(getInput())
      expect(screen.getByRole('option', { name: /Alpha Option/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Beta Option/i })).toBeInTheDocument()
    })

    it('calls onSearchChange with empty string when closed', async () => {
      const user = userEvent.setup()
      const onSearchChange = vi.fn()
      renderSelect({ onSearchChange })

      await user.click(getInput())
      await user.type(getInput(), 'Beta')
      onSearchChange.mockClear()

      await user.keyboard('{Escape}')
      await waitFor(() => {
        expect(onSearchChange).toHaveBeenCalledWith('')
      })
    })
  })

  describe('Clear selection', () => {
    it('calls onChange with empty string when clear is clicked', async () => {
      const user = userEvent.setup()
      const { onChange } = renderSelect({ selected: 'opt-1' })

      await user.click(screen.getByRole('button', { name: 'Clear selection' }))

      expect(onChange).toHaveBeenCalledWith('')
    })
  })
})
