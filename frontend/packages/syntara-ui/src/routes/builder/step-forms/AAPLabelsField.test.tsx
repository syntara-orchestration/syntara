import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import { AAPLabelsField } from './AAPLabelsField'

function TestWrapper({
  children,
  defaultValues,
}: {
  children: React.ReactNode
  defaultValues?: Partial<AAPJobTemplateFormData>
}) {
  const methods = useForm<AAPJobTemplateFormData>({
    defaultValues: {
      name: '',
      organization_name: '',
      job_template_name: '',
      labels: [],
      ...defaultValues,
    },
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

const mockLabels = [
  { id: 1, name: 'production' },
  { id: 2, name: 'staging' },
  { id: 3, name: 'development' },
]

describe('AAPLabelsField', () => {
  it('renders with placeholder text when no labels selected', () => {
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    expect(screen.getByRole('button', { name: /Use default labels/i })).toBeInTheDocument()
    expect(screen.getByText(/Select labels to apply/i)).toBeInTheDocument()
  })

  it('shows selected labels as chips in toggle', () => {
    render(
      <TestWrapper defaultValues={{ labels: ['production', 'staging'] }}>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    expect(screen.getByText('production')).toBeInTheDocument()
    expect(screen.getByText('staging')).toBeInTheDocument()
  })

  it('opens menu and displays available labels when clicked', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Use default labels/i })
    await user.click(toggle)

    await waitFor(() => {
      const menu = screen.getByRole('listbox', { name: /Labels/i })
      expect(within(menu).getByText('production')).toBeInTheDocument()
      expect(within(menu).getByText('staging')).toBeInTheDocument()
      expect(within(menu).getByText('development')).toBeInTheDocument()
    })
  })

  it('selects and deselects labels', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Use default labels/i })
    await user.click(toggle)

    // Select first label - find by text in menu and click its checkbox
    const menu = await screen.findByRole('listbox', { name: /Labels/i })
    const menuItems = within(menu).getAllByRole('menuitem')
    const prodMenuItem = menuItems.find((item) => item.textContent?.includes('production'))
    expect(prodMenuItem).toBeInTheDocument()

    const prodCheckbox = within(prodMenuItem!).getByRole('checkbox')
    await user.click(prodCheckbox)

    // Verify label chip appears in toggle
    await waitFor(() => {
      const chips = screen.getAllByText('production')
      expect(chips.length).toBeGreaterThan(1)
    })

    // Select second label
    const stagingMenuItem = menuItems.find((item) => item.textContent?.includes('staging'))
    const stagingCheckbox = within(stagingMenuItem!).getByRole('checkbox')
    await user.click(stagingCheckbox)

    // Verify both label chips are shown
    await waitFor(() => {
      const prodChips = screen.getAllByText('production')
      const stagingChips = screen.getAllByText('staging')
      expect(prodChips.length).toBeGreaterThan(1)
      expect(stagingChips.length).toBeGreaterThan(1)
    })

    // Deselect first label
    await user.click(prodCheckbox)

    // Verify only staging label chip remains in toggle
    await waitFor(() => {
      const stagingChips = screen.getAllByText('staging')
      expect(stagingChips.length).toBeGreaterThan(1)
    })

    // Production should only appear in menu, not in toggle
    const allButtons = screen.getAllByRole('button')
    const toggleButton = allButtons.find((btn) => btn.className.includes('pf-v6-c-menu-toggle'))
    expect(toggleButton).toBeInTheDocument()
    expect(within(toggleButton!).queryByText('production')).not.toBeInTheDocument()
    expect(within(toggleButton!).getByText('staging')).toBeInTheDocument()
  })

  it('displays selected labels as non-dismissible chips in toggle', () => {
    render(
      <TestWrapper defaultValues={{ labels: ['production', 'staging'] }}>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    // Verify both labels are present as non-dismissible chips in the toggle
    const allButtons = screen.getAllByRole('button')
    const toggle = allButtons.find((btn) => btn.className.includes('pf-v6-c-menu-toggle'))
    expect(toggle).toBeInTheDocument()
    expect(within(toggle!).getByText('production')).toBeInTheDocument()
    expect(within(toggle!).getByText('staging')).toBeInTheDocument()

    // Verify no close buttons on the labels (they are not dismissible from the toggle)
    const closeButtons = screen.queryAllByRole('button', { name: /Close/i })
    expect(closeButtons).toHaveLength(0)
  })

  it('filters labels based on search input', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    // Find search input
    const searchInput = screen.getByPlaceholderText('Search labels')
    await user.type(searchInput, 'prod')

    await waitFor(() => {
      const menu = screen.getByRole('listbox', { name: /Labels/i })
      // Should show only production
      expect(within(menu).getByText('production')).toBeInTheDocument()
      expect(within(menu).queryByText('staging')).not.toBeInTheDocument()
      expect(within(menu).queryByText('development')).not.toBeInTheDocument()
    })
  })

  it('shows create new label option when filter does not match existing labels', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    const searchInput = screen.getByPlaceholderText('Search labels')
    await user.type(searchInput, 'new-label')

    await waitFor(() => {
      expect(screen.getByText('Create new label')).toBeInTheDocument()
      expect(screen.getByText('new-label')).toBeInTheDocument()
    })
  })

  it('creates and selects a new custom label', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    const searchInput = screen.getByPlaceholderText('Search labels')
    await user.type(searchInput, 'custom-label')

    // Find the create new label option
    await waitFor(() => {
      expect(screen.getByText('Create new label')).toBeInTheDocument()
    })

    const menu = screen.getByRole('listbox', { name: /Labels/i })
    const menuItems = within(menu).getAllByRole('menuitem')
    const createMenuItem = menuItems.find((item) => item.textContent?.includes('Create new label'))
    const customCheckbox = within(createMenuItem!).getByRole('checkbox')
    await user.click(customCheckbox)

    // Verify custom label appears as chip in toggle
    await waitFor(() => {
      const chips = screen.getAllByText('custom-label')
      expect(chips.length).toBeGreaterThan(0)
    })
  })

  it('displays custom labels alongside known labels', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper defaultValues={{ labels: ['production', 'custom-label'] }}>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    // Verify both labels are shown as chips in toggle (non-dismissible)
    expect(screen.getByText('production')).toBeInTheDocument()
    expect(screen.getByText('custom-label')).toBeInTheDocument()

    // Open menu and verify both appear in the list
    const toggle = screen.getByRole('button', { expanded: false })
    await user.click(toggle)

    await waitFor(() => {
      const menu = screen.getByRole('listbox', { name: /Labels/i })
      const menuItems = within(menu).getAllByRole('menuitem')
      const prodItem = menuItems.find((item) => item.textContent === 'production')
      const customItem = menuItems.find((item) => item.textContent === 'custom-label')
      expect(prodItem).toBeInTheDocument()
      expect(customItem).toBeInTheDocument()
    })
  })

  it('clears search filter when menu is closed', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    let searchInput = screen.getByPlaceholderText('Search labels')
    await user.type(searchInput, 'prod')

    // Verify filtered state
    await waitFor(() => {
      const menu = screen.getByRole('listbox', { name: /Labels/i })
      expect(within(menu).getByText('production')).toBeInTheDocument()
      expect(within(menu).queryByText('staging')).not.toBeInTheDocument()
    })

    // Close menu by clicking outside or pressing escape
    await user.keyboard('{Escape}')

    // Wait for menu to close
    await waitFor(() => {
      expect(screen.queryByRole('listbox', { name: /Labels/i })).not.toBeInTheDocument()
    })

    // Reopen menu
    await user.click(toggle)

    // Search input should be cleared and all labels visible
    await waitFor(() => {
      searchInput = screen.getByPlaceholderText('Search labels')
      expect(searchInput).toHaveValue('')
    })

    const menu = screen.getByRole('listbox', { name: /Labels/i })
    expect(within(menu).getByText('production')).toBeInTheDocument()
    expect(within(menu).getByText('staging')).toBeInTheDocument()
    expect(within(menu).getByText('development')).toBeInTheDocument()
  })

  it('shows loading spinner when isLoading is true', () => {
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={[]}
          isLoading={true}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    expect(screen.getByRole('button', { name: /Use default labels/i })).toBeDisabled()
  })

  it('shows "No labels available" when labels array is empty and not loading', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={[]}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Use default labels/i })
    await user.click(toggle)

    await waitFor(() => {
      expect(screen.getByText('No labels available')).toBeInTheDocument()
    })
  })

  it('calls onSearchChange when search input changes with debounce', async () => {
    const onSearchChange = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
          onSearchChange={onSearchChange}
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    const searchInput = screen.getByPlaceholderText('Search labels')
    await user.type(searchInput, 'prod')

    // Verify debounced search callback was called
    await waitFor(
      () => {
        expect(onSearchChange).toHaveBeenCalledWith('prod')
      },
      { timeout: 500 }
    )
  })

  it('handles non-array field values gracefully', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper defaultValues={{ labels: undefined as unknown as string[] }}>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    // Should render without errors
    const toggle = screen.getByRole('button', { name: /Use default labels/i })
    expect(toggle).toBeInTheDocument()

    await user.click(toggle)

    // Should be able to select labels
    const menu = await screen.findByRole('listbox', { name: /Labels/i })
    const prodCheckbox = within(menu).getByLabelText('production', { selector: 'input[type="checkbox"]' })
    await user.click(prodCheckbox)

    await waitFor(() => {
      expect(screen.getAllByText('production').length).toBeGreaterThan(1)
    })
  })

  it('case-insensitive filtering works correctly', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    const searchInput = screen.getByPlaceholderText('Search labels')
    await user.type(searchInput, 'PROD')

    await waitFor(() => {
      const menu = screen.getByRole('listbox', { name: /Labels/i })
      expect(within(menu).getByText('production')).toBeInTheDocument()
      expect(within(menu).queryByText('staging')).not.toBeInTheDocument()
    })
  })

  it('trims whitespace when creating new labels', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    const searchInput = screen.getByPlaceholderText('Search labels')
    await user.type(searchInput, '  trimmed  ')

    await waitFor(() => {
      // Should show create option with trimmed value
      expect(screen.getByText('trimmed')).toBeInTheDocument()
      expect(screen.getByText('Create new label')).toBeInTheDocument()
    })
  })

  it('does not show create option for empty search', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    await waitFor(() => {
      expect(screen.queryByText('Create new label')).not.toBeInTheDocument()
    })
  })

  it('clears search input when clear button is clicked', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Search labels"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /Search labels/i })
    await user.click(toggle)

    const searchInput = screen.getByPlaceholderText('Search labels')
    await user.type(searchInput, 'prod')

    // Find and click the clear button (labeled as "Reset" by PatternFly SearchInput)
    const clearButton = screen.getByRole('button', { name: /Reset/i })
    await user.click(clearButton)

    await waitFor(() => {
      expect(searchInput).toHaveValue('')
      const menu = screen.getByRole('listbox', { name: /Labels/i })
      // All labels should be visible
      expect(within(menu).getByText('production')).toBeInTheDocument()
      expect(within(menu).getByText('staging')).toBeInTheDocument()
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <TestWrapper>
        <AAPLabelsField
          label="Labels"
          fieldId="test-labels"
          availableLabels={mockLabels}
          isLoading={false}
          helperText="Select labels to apply"
          placeholderText="Use default labels"
        />
      </TestWrapper>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
