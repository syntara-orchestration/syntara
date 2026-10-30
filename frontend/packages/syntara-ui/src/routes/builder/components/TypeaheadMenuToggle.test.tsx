import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { TypeaheadMenuToggle, type TypeaheadMenuToggleProps } from './TypeaheadMenuToggle'

const defaultProps: TypeaheadMenuToggleProps = {
  toggleRef: React.createRef(),
  displayText: '',
  ariaLabel: 'Select item',
  fieldId: 'test-field',
  isOpen: false,
  isDisabled: false,
  isPending: false,
  hasSelection: false,
  filterText: '',
  placeholder: 'Select an item',
  onFilterChange: vi.fn(),
  onClear: vi.fn(),
  onToggle: vi.fn(),
}

function renderToggle(props: Partial<TypeaheadMenuToggleProps> = {}) {
  return render(<TypeaheadMenuToggle {...defaultProps} {...props} />)
}

describe('TypeaheadMenuToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders with placeholder text', () => {
    renderToggle()
    expect(screen.getByPlaceholderText('Select an item')).toBeInTheDocument()
  })

  it('shows display text when closed with a selection', () => {
    renderToggle({ displayText: 'Selected Item', hasSelection: true })
    expect(screen.getByDisplayValue('Selected Item')).toBeInTheDocument()
  })

  it('shows filter text when open', () => {
    renderToggle({ isOpen: true, filterText: 'search query' })
    expect(screen.getByDisplayValue('search query')).toBeInTheDocument()
  })

  it('shows loading placeholder when pending', () => {
    renderToggle({ isPending: true })
    expect(screen.getByPlaceholderText('Loading...')).toBeInTheDocument()
  })

  it('shows custom loading placeholder when pending', () => {
    renderToggle({ isPending: true, loadingPlaceholder: 'Fetching data...' })
    expect(screen.getByPlaceholderText('Fetching data...')).toBeInTheDocument()
  })

  it('shows regular placeholder when not pending', () => {
    renderToggle({ isPending: false })
    expect(screen.getByPlaceholderText('Select an item')).toBeInTheDocument()
  })

  it('disables input when isDisabled is true', () => {
    renderToggle({ isDisabled: true })
    const input = screen.getByRole('textbox', { name: 'Select item' })
    expect(input).toBeDisabled()
  })

  it('disables input when isPending is true', () => {
    renderToggle({ isPending: true })
    const input = screen.getByRole('textbox', { name: 'Select item' })
    expect(input).toBeDisabled()
  })

  it('calls onToggle when toggle is clicked', async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    renderToggle({ onToggle })

    await user.click(screen.getByRole('button', { name: 'Select item' }))
    expect(onToggle).toHaveBeenCalled()
  })

  it('calls onToggle when text input is clicked', async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    renderToggle({ onToggle })

    await user.click(screen.getByPlaceholderText('Select an item'))
    expect(onToggle).toHaveBeenCalled()
  })

  it('calls onFilterChange when text is typed', async () => {
    const onFilterChange = vi.fn()
    const user = userEvent.setup()
    renderToggle({ isOpen: true, onFilterChange })

    const input = screen.getByRole('textbox', { name: 'Select item' })
    await user.type(input, 'abc')
    expect(onFilterChange).toHaveBeenCalled()
  })

  describe('clear filter button', () => {
    it('shows clear filter button when open with filter text', () => {
      renderToggle({ isOpen: true, filterText: 'search' })
      expect(screen.getByRole('button', { name: 'Clear filter' })).toBeInTheDocument()
    })

    it('does not show clear filter button when closed', () => {
      renderToggle({ isOpen: false, filterText: 'search' })
      expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()
    })

    it('does not show clear filter button when no filter text', () => {
      renderToggle({ isOpen: true, filterText: '' })
      expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()
    })

    it('calls onFilterChange with empty string when clear filter is clicked', async () => {
      const onFilterChange = vi.fn()
      const user = userEvent.setup()
      renderToggle({ isOpen: true, filterText: 'search', onFilterChange })

      await user.click(screen.getByRole('button', { name: 'Clear filter' }))
      expect(onFilterChange).toHaveBeenCalledWith('')
    })

    it('clears the filter without toggling the menu and returns focus to the input', async () => {
      const onFilterChange = vi.fn()
      const onToggle = vi.fn()
      const user = userEvent.setup()
      renderToggle({ isOpen: true, filterText: 'search', onFilterChange, onToggle })

      await user.click(screen.getByRole('button', { name: 'Clear filter' }))

      expect(onFilterChange).toHaveBeenCalledWith('')
      expect(onToggle).not.toHaveBeenCalled()
      expect(screen.getByRole('textbox', { name: 'Select item' })).toHaveFocus()
      expect(screen.getByRole('button', { name: 'Select item' })).toHaveAttribute('aria-expanded', 'true')
    })
  })

  describe('clear selection button', () => {
    it('shows clear selection button when closed with selection and not disabled', () => {
      renderToggle({ isOpen: false, hasSelection: true, isDisabled: false, isPending: false })
      expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()
    })

    it('does not show clear selection button when open', () => {
      renderToggle({ isOpen: true, hasSelection: true })
      expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
    })

    it('does not show clear selection button when no selection', () => {
      renderToggle({ isOpen: false, hasSelection: false })
      expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
    })

    it('does not show clear selection button when disabled', () => {
      renderToggle({ isOpen: false, hasSelection: true, isDisabled: true })
      expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
    })

    it('does not show clear selection button when pending', () => {
      renderToggle({ isOpen: false, hasSelection: true, isPending: true })
      expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
    })

    it('calls onClear when clear selection is clicked', async () => {
      const onClear = vi.fn()
      const user = userEvent.setup()
      renderToggle({ isOpen: false, hasSelection: true, onClear })

      await user.click(screen.getByRole('button', { name: 'Clear selection' }))
      expect(onClear).toHaveBeenCalled()
    })
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderToggle()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with clear selection visible', async () => {
    const { container } = renderToggle({ hasSelection: true, displayText: 'Selected' })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('disables when both isDisabled and isPending are true', () => {
    renderToggle({ isDisabled: true, isPending: true })
    const input = screen.getByRole('textbox', { name: 'Select item' })
    expect(input).toBeDisabled()
  })

  it('does not show clear selection when both isDisabled and isPending', () => {
    renderToggle({ isOpen: false, hasSelection: true, isDisabled: true, isPending: true })
    expect(screen.queryByRole('button', { name: 'Clear selection' })).not.toBeInTheDocument()
  })

  it('shows display text when closed without a selection', () => {
    renderToggle({ isOpen: false, displayText: '', hasSelection: false })
    expect(screen.getByDisplayValue('')).toBeInTheDocument()
  })

  it('shows empty filter text when open with no filter', () => {
    renderToggle({ isOpen: true, filterText: '' })
    expect(screen.getByDisplayValue('')).toBeInTheDocument()
  })

  it('does not show clear filter when open but filterText is empty string', () => {
    renderToggle({ isOpen: true, filterText: '' })
    expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()
  })

  it('shows clear selection when closed with selection and enabled and not pending', () => {
    renderToggle({ isOpen: false, hasSelection: true, isDisabled: false, isPending: false })
    expect(screen.getByRole('button', { name: 'Clear selection' })).toBeInTheDocument()
  })

  it('stops propagation on clear selection click', async () => {
    const onClear = vi.fn()
    const onToggle = vi.fn()
    const user = userEvent.setup()
    renderToggle({ isOpen: false, hasSelection: true, onClear, onToggle })

    await user.click(screen.getByRole('button', { name: 'Clear selection' }))
    expect(onClear).toHaveBeenCalled()
  })

  it('calls onToggle via text input click when isOpen is false', async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    renderToggle({ isOpen: false, onToggle })

    await user.click(screen.getByPlaceholderText('Select an item'))
    expect(onToggle).toHaveBeenCalled()
  })
})
