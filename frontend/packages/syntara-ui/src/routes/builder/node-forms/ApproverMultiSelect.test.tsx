import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ApproverMultiSelect, type SelectableItem } from './ApproverMultiSelect'

type TestItem = SelectableItem & { name: string }

const mockItems: TestItem[] = [
  { id: 'item-1', name: 'Alice' },
  { id: 'item-2', name: 'Bob' },
  { id: 'item-3', name: 'Charlie' },
]

const defaultProps = {
  value: [] as string[],
  onChange: vi.fn(),
  items: mockItems,
  isLoading: false,
  getItemId: (item: TestItem) => item.id,
  getItemValue: (item: TestItem) => item.name,
  getItemLabel: (item: TestItem) => item.name,
  placeholderText: 'Select items',
  emptyText: 'No items available',
  loadingText: 'Loading...',
  helperText: 'Choose one or more items',
}

describe('ApproverMultiSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('custom value entry', () => {
    it('adds a custom value on Enter when allowCustomValue is true', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(<ApproverMultiSelect<TestItem> {...defaultProps} items={[]} onChange={onChange} allowCustomValue />)

      const input = screen.getByPlaceholderText('Select items')
      await user.click(input)
      await user.type(input, 'custom-user')
      await user.keyboard('{Enter}')

      expect(onChange).toHaveBeenCalledWith(['custom-user'])
    })

    it('does not add custom value on Enter when allowCustomValue is false', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(<ApproverMultiSelect<TestItem> {...defaultProps} items={[]} onChange={onChange} />)

      const input = screen.getByPlaceholderText('Select items')
      await user.click(input)
      await user.type(input, 'custom-user')
      await user.keyboard('{Enter}')

      expect(onChange).not.toHaveBeenCalled()
    })

    it('does not add duplicate custom values', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <ApproverMultiSelect<TestItem>
          {...defaultProps}
          value={['existing-user']}
          items={[]}
          onChange={onChange}
          allowCustomValue
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'existing-user')
      await user.keyboard('{Enter}')

      expect(onChange).not.toHaveBeenCalled()
    })

    it('ignores Enter with empty input when allowCustomValue is true', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(<ApproverMultiSelect<TestItem> {...defaultProps} items={[]} onChange={onChange} allowCustomValue />)

      const input = screen.getByPlaceholderText('Select items')
      await user.click(input)
      await user.keyboard('{Enter}')

      expect(onChange).not.toHaveBeenCalled()
    })
  })

  describe('chip display for custom values', () => {
    it('renders chips for custom values not in items list', () => {
      render(<ApproverMultiSelect<TestItem> {...defaultProps} value={['custom-user']} items={[]} allowCustomValue />)

      expect(screen.getByText('custom-user')).toBeInTheDocument()
    })

    it('renders chips for both item-backed and custom values', () => {
      render(<ApproverMultiSelect<TestItem> {...defaultProps} value={['Alice', 'manual-entry']} allowCustomValue />)

      expect(screen.getByText('Alice')).toBeInTheDocument()
      expect(screen.getByText('manual-entry')).toBeInTheDocument()
    })

    it('allows removing custom value chips', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <ApproverMultiSelect<TestItem>
          {...defaultProps}
          value={['custom-user']}
          items={[]}
          onChange={onChange}
          allowCustomValue
        />
      )

      const closeButton = screen.getByRole('button', { name: /close/i })
      await user.click(closeButton)

      expect(onChange).toHaveBeenCalledWith([])
    })
  })

  describe('accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<ApproverMultiSelect<TestItem> {...defaultProps} />)
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with custom values', async () => {
      const { container } = render(
        <ApproverMultiSelect<TestItem> {...defaultProps} value={['custom-user']} items={[]} allowCustomValue />
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with validation error', async () => {
      const { container } = render(
        <ApproverMultiSelect<TestItem> {...defaultProps} validationError={{ message: 'Required field' }} />
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('standard select behavior', () => {
    it('selects items from the dropdown', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(<ApproverMultiSelect<TestItem> {...defaultProps} onChange={onChange} />)

      await user.click(screen.getByPlaceholderText('Select items'))

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Alice'))

      expect(onChange).toHaveBeenCalledWith(['Alice'])
    })

    it('clears all selections', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(<ApproverMultiSelect<TestItem> {...defaultProps} value={['Alice', 'Bob']} onChange={onChange} />)

      await user.click(screen.getByRole('button', { name: /clear all/i }))

      expect(onChange).toHaveBeenCalledWith([])
    })

    it('shows empty text when no items match filter', async () => {
      const user = userEvent.setup()

      render(<ApproverMultiSelect<TestItem> {...defaultProps} />)

      const input = screen.getByPlaceholderText('Select items')
      await user.click(input)
      await user.type(input, 'nonexistent')

      expect(screen.getByText('No items available')).toBeInTheDocument()
    })

    it('shows loading text when loading', async () => {
      const user = userEvent.setup()

      render(<ApproverMultiSelect<TestItem> {...defaultProps} isLoading />)

      await user.click(screen.getByRole('textbox'))

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })
  })
})
