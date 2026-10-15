import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import { AAPResourceMultiSelectField } from './AAPResourceMultiSelectField'

function TestWrapper({
  children,
  defaultValues,
}: {
  children: React.ReactNode
  defaultValues?: Partial<AAPJobTemplateFormData>
}) {
  const methods = useForm<AAPJobTemplateFormData>({
    defaultValues: {
      job_credentials: [],
      ...defaultValues,
    },
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

describe('AAPResourceMultiSelectField', () => {
  const mockItems = [
    { id: 1, name: 'Credential 1' },
    { id: 2, name: 'Credential 2' },
    { id: 3, name: 'Credential 3' },
  ]

  it('renders with placeholder when no items selected', () => {
    render(
      <TestWrapper>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
        />
      </TestWrapper>
    )

    expect(screen.getByText('No credentials selected')).toBeInTheDocument()
    expect(screen.getByText('Select credentials')).toBeInTheDocument()
  })

  it('renders with loading spinner when isLoading=true', () => {
    render(
      <TestWrapper>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={[]}
          isLoading={true}
          helperText="Select credentials"
          placeholderText="No credentials selected"
        />
      </TestWrapper>
    )

    // eslint-disable-next-line testing-library/no-node-access -- checking for PatternFly spinner icon
    expect(document.querySelector('.pf-v6-c-spinner')).toBeInTheDocument()
  })

  it('displays selected items as labels', () => {
    render(
      <TestWrapper defaultValues={{ job_credentials: [1, 3] }}>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
        />
      </TestWrapper>
    )

    expect(screen.getByText('Credential 1')).toBeInTheDocument()
    expect(screen.getByText('Credential 3')).toBeInTheDocument()
  })

  it('opens dropdown and displays items', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /no credentials selected/i })
    await user.click(toggle)

    await waitFor(() => {
      expect(screen.getByText('Credential 1')).toBeVisible()
    })
    expect(screen.getByText('Credential 2')).toBeVisible()
    expect(screen.getByText('Credential 3')).toBeVisible()
  })

  it('handles legacy single-value data by converting to array', () => {
    render(
      // Testing legacy data format where job_credentials was incorrectly stored as a number instead of number[]
      <TestWrapper defaultValues={{ job_credentials: 2 as unknown as number[] }}>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
        />
      </TestWrapper>
    )

    expect(screen.getByText('Credential 2')).toBeInTheDocument()
  })

  it('handles undefined/null value gracefully', () => {
    render(
      <TestWrapper defaultValues={{ job_credentials: undefined }}>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
        />
      </TestWrapper>
    )

    expect(screen.getByText('No credentials selected')).toBeInTheDocument()
  })

  it('sets aria-describedby on toggle for helper text', () => {
    render(
      <TestWrapper>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /no credentials selected/i })
    expect(toggle).toHaveAttribute('aria-describedby', 'test-multiselect-helper')
  })

  it('renders search input when onSearchChange is provided', async () => {
    const user = userEvent.setup()
    const mockSearchChange = vi.fn()

    render(
      <TestWrapper>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
          onSearchChange={mockSearchChange}
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /no credentials selected/i })
    await user.click(toggle)

    const searchInput = await screen.findByPlaceholderText('Search')
    expect(searchInput).toBeInTheDocument()

    await user.type(searchInput, 'test')

    await waitFor(
      () => {
        expect(mockSearchChange).toHaveBeenCalledWith('test')
      },
      { timeout: 500 }
    )
  })

  it('displays "No items available" when items array is empty and not loading', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={[]}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /no credentials selected/i })
    await user.click(toggle)

    await waitFor(() => {
      expect(screen.getByText('No items available')).toBeInTheDocument()
    })
  })

  it('merges defaultValues into items list when provided', () => {
    const defaultValues = [
      { id: 99, name: 'Default Credential' },
      { id: 1, name: 'Credential 1' },
    ]

    render(
      <TestWrapper defaultValues={{ job_credentials: [99] }}>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
          defaultValues={defaultValues}
        />
      </TestWrapper>
    )

    // Default credential appears in the toggle as selected label
    expect(screen.getAllByText('Default Credential').length).toBeGreaterThan(0)
  })

  it('clears search filter when dropdown is closed', async () => {
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
          onSearchChange={vi.fn()}
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /no credentials selected/i })
    await user.click(toggle)

    const searchInput = await screen.findByPlaceholderText('Search')
    await user.type(searchInput, 'Credential 1')
    expect(searchInput).toHaveValue('Credential 1')

    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Search')).not.toBeInTheDocument()
    })

    await user.click(toggle)
    expect(await screen.findByPlaceholderText('Search')).toHaveValue('')
  })

  it('debounces search callback', async () => {
    const user = userEvent.setup()
    const mockSearchChange = vi.fn()

    render(
      <TestWrapper>
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="test-multiselect"
          nameField="job_credentials"
          items={mockItems}
          isLoading={false}
          helperText="Select credentials"
          placeholderText="No credentials selected"
          onSearchChange={mockSearchChange}
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /no credentials selected/i })
    await user.click(toggle)

    const searchInput = await screen.findByPlaceholderText('Search')
    await user.type(searchInput, 'abc')

    expect(mockSearchChange).not.toHaveBeenCalled()

    await waitFor(
      () => {
        expect(mockSearchChange).toHaveBeenCalledWith('abc')
      },
      { timeout: 500 }
    )

    expect(mockSearchChange).toHaveBeenCalledTimes(1)
  })
})
