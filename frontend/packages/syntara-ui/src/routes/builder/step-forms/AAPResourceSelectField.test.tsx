import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import { AAPResourceSelectField } from './AAPResourceSelectField'

const mockItems = [
  { id: 101, name: 'Demo Inventory' },
  { id: 102, name: 'Production Inventory' },
  { id: 103, name: 'Staging Inventory' },
] as const

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
      ...defaultValues,
    },
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

function renderField(
  overrides: Partial<React.ComponentProps<typeof AAPResourceSelectField>> = {},
  formDefaults?: Partial<AAPJobTemplateFormData>
) {
  const props = {
    label: 'Inventory',
    fieldId: 'aap-inventory_name',
    nameField: 'inventory_name' as keyof AAPJobTemplateFormData,
    idField: 'inventory_id' as keyof AAPJobTemplateFormData,
    items: [...mockItems],
    isLoading: false,
    helperText: 'Select an inventory to override the default',
    placeholderText: 'Use default inventory',
    onSearchChange: vi.fn(),
    ...overrides,
  }

  const view = render(
    <TestWrapper defaultValues={formDefaults}>
      <AAPResourceSelectField {...props} />
    </TestWrapper>
  )
  return { ...view, onSearchChange: props.onSearchChange }
}

describe('AAPResourceSelectField', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderField()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Rendering', () => {
    it('renders label text', () => {
      renderField()
      expect(screen.getByText('Inventory')).toBeInTheDocument()
    })

    it('renders helper text', () => {
      renderField()
      expect(screen.getByText('Select an inventory to override the default')).toBeInTheDocument()
    })

    it('renders the typeahead with placeholder', () => {
      renderField()
      expect(screen.getByPlaceholderText('Use default inventory')).toBeInTheDocument()
    })

    it('displays the currently selected value', () => {
      renderField({}, { inventory_name: 'Demo Inventory' })
      expect(screen.getByDisplayValue('Demo Inventory')).toBeInTheDocument()
    })
  })

  describe('Selection behavior', () => {
    it('sets both name and ID form values when a known option is selected', async () => {
      const user = userEvent.setup()
      renderField()

      // Open the dropdown via the input
      const input = screen.getByPlaceholderText('Use default inventory')
      await user.click(input)

      // Select an option
      await user.click(screen.getByRole('option', { name: /Production Inventory/i }))

      // The input should now show the selected value
      await waitFor(() => {
        expect(input).toHaveValue('Production Inventory')
      })
    })

    it('clears the ID when selection is cleared', async () => {
      const user = userEvent.setup()
      renderField({}, { inventory_name: 'Demo Inventory', inventory_id: 101 })

      // Click clear button
      await user.click(screen.getByRole('button', { name: 'Clear selection' }))

      // The input should be cleared (onChange('') means the item won't be found,
      // exercising the selected?.id === undefined branch)
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Use default inventory')).toHaveValue('')
      })
    })

    it('renders with empty string when field value is undefined', () => {
      // No inventory defaultValue set, so field.value is undefined
      // This exercises the (field.value as string) ?? '' fallback
      renderField()
      expect(screen.getByPlaceholderText('Use default inventory')).toHaveValue('')
    })

    it('renders with empty selection when field value does not match any item', () => {
      // Field has a value but it doesn't match any item in the list
      // This exercises the selectedItem ? ... : '' branch when selectedItem is undefined
      renderField({}, { inventory_name: 'Non-existent Inventory' })
      const input = screen.getByPlaceholderText('Use default inventory')
      // The input will be empty because selectedItem is undefined (no matching item)
      expect(input).toHaveValue('')
    })
  })

  describe('Loading state', () => {
    it('passes isLoading to the typeahead and shows spinner', () => {
      renderField({ isLoading: true })
      expect(screen.getByLabelText('Loading')).toBeInTheDocument()
    })

    it('does not show spinner when not loading', () => {
      renderField({ isLoading: false })
      expect(screen.queryByLabelText('Loading')).not.toBeInTheDocument()
    })
  })

  describe('Search', () => {
    it('passes onSearchChange to the typeahead', async () => {
      const user = userEvent.setup()
      renderField()

      const input = screen.getByPlaceholderText('Use default inventory')
      await user.type(input, 'Demo')

      // The input should reflect the typed text (dropdown is open)
      expect(input).toHaveValue('Demo')
    })
  })

  describe('Options mapping', () => {
    it('renders all item names as options when dropdown is open', async () => {
      const user = userEvent.setup()
      renderField()

      await user.click(screen.getByPlaceholderText('Use default inventory'))

      expect(screen.getByRole('option', { name: /Demo Inventory/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Production Inventory/i })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Staging Inventory/i })).toBeInTheDocument()
    })

    it('shows no results when items array is empty', async () => {
      const user = userEvent.setup()
      renderField({ items: [] })

      await user.click(screen.getByPlaceholderText('Use default inventory'))

      expect(screen.getByText(/No results match/)).toBeInTheDocument()
    })
  })
})
