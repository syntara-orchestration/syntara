import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'

import type { useAAPBrowser } from '../../../hooks/useAAPBrowser'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import { AAPResourcePickers } from './AAPResourcePickers'

// Mock dependencies
// CredentialSelector moved to AAPStepForm — no longer rendered in AAPResourcePickers

vi.mock('../../../utils/apiErrors', () => ({
  getErrorMessage: (error: Error) => error.message,
  isRetryableError: () => true,
}))

vi.mock('../../../utils/urlValidation', () => ({
  isValidAAPTemplateURL: (url: string) => url.startsWith('https://'),
}))

vi.mock('./AAPTypeaheadSelect', () => ({
  AAPTypeaheadSelect: ({
    options,
    onChange,
    placeholder,
    selected,
    ariaLabel,
  }: {
    options: Array<{ value: string; label: string }>
    onChange: (v: string) => void
    placeholder: string
    selected: string
    ariaLabel: string
  }) => (
    <div data-testid={`typeahead-${ariaLabel.toLowerCase()}`}>
      <input
        aria-label={ariaLabel}
        value={selected}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      {options.map((opt) => (
        <button key={opt.value} onClick={() => onChange(opt.value)}>
          {opt.label}
        </button>
      ))}
    </div>
  ),
}))

function TestWrapper({
  children,
  defaultValues,
}: {
  children: React.ReactNode
  defaultValues?: Partial<AAPJobTemplateFormData>
}) {
  const methods = useForm<AAPJobTemplateFormData>({
    defaultValues,
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

function createMockBrowser(overrides?: Partial<ReturnType<typeof useAAPBrowser>>): ReturnType<typeof useAAPBrowser> {
  return {
    organizations: [
      { id: 1, name: 'Org 1' },
      { id: 2, name: 'Org 2' },
    ],
    jobTemplates: [
      { id: 1, name: 'Template 1', description: 'Desc 1' },
      { id: 2, name: 'Template 2', description: null },
    ],
    selectOrganization: vi.fn(),
    selectJobTemplate: vi.fn(),
    searchOrganizations: vi.fn(),
    searchJobTemplates: vi.fn(),
    loadingOrgs: false,
    loadingTemplates: false,
    error: null,
    retryAll: vi.fn(),
    templateDetail: undefined,
    ...overrides,
  } as ReturnType<typeof useAAPBrowser>
}

describe('AAPResourcePickers', () => {
  it('renders organization selector with options', () => {
    const browser = createMockBrowser()
    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Organization')).toBeInTheDocument()
    expect(screen.getByText('Org 1')).toBeInTheDocument()
    expect(screen.getByText('Org 2')).toBeInTheDocument()
  })

  it('renders job template selector with options', () => {
    const browser = createMockBrowser()
    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Job template')).toBeInTheDocument()
    expect(screen.getByText('Template 1')).toBeInTheDocument()
    expect(screen.getByText('Template 2')).toBeInTheDocument()
  })

  it('calls selectOrganization when organization is changed', async () => {
    const user = userEvent.setup()
    const selectOrganization = vi.fn()
    const browser = createMockBrowser({ selectOrganization })

    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    const orgButton = screen.getByRole('button', { name: 'Org 1' })
    await user.click(orgButton)

    expect(selectOrganization).toHaveBeenCalledWith('Org 1')
  })

  it('calls selectJobTemplate when template is changed', async () => {
    const user = userEvent.setup()
    const selectJobTemplate = vi.fn()
    const browser = createMockBrowser({ selectJobTemplate })

    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    const templateButton = screen.getByRole('button', { name: 'Template 1' })
    await user.click(templateButton)

    expect(selectJobTemplate).toHaveBeenCalledWith(1)
  })

  it('displays error alert when browser has error', () => {
    const browser = createMockBrowser({ error: new Error('Failed to load resources') })

    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.getByText('Failed to load AAP resources')).toBeInTheDocument()
    expect(screen.getByText('Failed to load resources')).toBeInTheDocument()
  })

  it('shows retry button for retryable errors', async () => {
    const user = userEvent.setup()
    const retryAll = vi.fn()
    const browser = createMockBrowser({
      error: new Error('Network error'),
      retryAll,
    })

    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    const retryButton = screen.getByRole('button', { name: /retry/i })
    await user.click(retryButton)

    expect(retryAll).toHaveBeenCalled()
  })

  it('displays template link when template detail has valid URL', () => {
    const browser = createMockBrowser({
      templateDetail: {
        id: 1,
        url: 'https://aap.example.com/templates/1',
      } as NonNullable<ReturnType<typeof useAAPBrowser>['templateDetail']>,
    })

    render(
      <TestWrapper defaultValues={{ job_template_name: 'Template 1' }}>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    const link = screen.getByRole('link', { name: /view job template in aap/i })
    expect(link).toHaveAttribute('href', 'https://aap.example.com/templates/1')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('does not display template link for invalid URLs', () => {
    const browser = createMockBrowser({
      templateDetail: {
        id: 1,
        url: 'invalid-url',
      } as NonNullable<ReturnType<typeof useAAPBrowser>['templateDetail']>,
    })

    render(
      <TestWrapper defaultValues={{ job_template_name: 'Template 1' }}>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.queryByRole('link', { name: /view job template in aap/i })).not.toBeInTheDocument()
  })

  it('maps organizations to options correctly', () => {
    const browser = createMockBrowser()

    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    // Options should include all organizations
    expect(screen.getByText('Org 1')).toBeInTheDocument()
    expect(screen.getByText('Org 2')).toBeInTheDocument()
  })

  it('maps job templates to options with descriptions', () => {
    const browser = createMockBrowser()

    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    // Both templates should be rendered
    expect(screen.getByText('Template 1')).toBeInTheDocument()
    expect(screen.getByText('Template 2')).toBeInTheDocument()
  })

  it('clears job template and prompt overrides when organization changes', async () => {
    const user = userEvent.setup()
    const selectOrganization = vi.fn()
    const browser = createMockBrowser({ selectOrganization })

    render(
      <TestWrapper
        defaultValues={{
          organization_name: 'Org 1',
          job_template_name: 'Template 1',
          job_template_id: 1,
          inventory_name: 'Test Inventory',
        }}
      >
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    // Change organization - triggers clearPromptOverrides
    const orgButton = screen.getByRole('button', { name: 'Org 2' })
    await user.click(orgButton)

    // Verify selectOrganization was called
    expect(selectOrganization).toHaveBeenCalledWith('Org 2')
  })

  it('clears all prompt overrides when job template changes', async () => {
    const user = userEvent.setup()
    const selectJobTemplate = vi.fn()
    const browser = createMockBrowser({ selectJobTemplate })

    render(
      <TestWrapper
        defaultValues={{
          organization_name: 'Org 1',
          job_template_name: 'Template 1',
          job_template_id: 1,
          inventory_name: 'Old Inventory',
          extra_vars: '{"old": "value"}',
          limit: 'old-limit',
        }}
      >
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    // Change job template - triggers clearPromptOverrides
    const templateButton = screen.getByRole('button', { name: 'Template 2' })
    await user.click(templateButton)

    // Verify selectJobTemplate was called
    expect(selectJobTemplate).toHaveBeenCalledWith(2)
  })

  it('handles loading states', () => {
    const browser = createMockBrowser({ loadingOrgs: true, loadingTemplates: true })

    render(
      <TestWrapper>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    // Component should render even when loading
    expect(screen.getByLabelText('Organization')).toBeInTheDocument()
    expect(screen.getByLabelText('Job template')).toBeInTheDocument()
  })

  it('displays error states in form fields', () => {
    function FormWithErrors() {
      const methods = useForm<AAPJobTemplateFormData>({
        defaultValues: {},
        errors: {
          organization_name: { type: 'required', message: 'Organization is required' },
          job_template_name: { type: 'required', message: 'Job template is required' },
        },
      })

      // Set errors after initialization
      if (!methods.formState.errors.organization_name) {
        methods.setError('organization_name', { message: 'Organization is required' })
        methods.setError('job_template_name', { message: 'Job template is required' })
      }

      return (
        <FormProvider {...methods}>
          <AAPResourcePickers browser={createMockBrowser()} />
        </FormProvider>
      )
    }

    render(<FormWithErrors />)

    expect(screen.getByText('Organization is required')).toBeInTheDocument()
    expect(screen.getByText('Job template is required')).toBeInTheDocument()
  })

  it('does not render template link when templateDetail is undefined', () => {
    const browser = createMockBrowser({ templateDetail: undefined })

    render(
      <TestWrapper defaultValues={{ job_template_name: 'Template 1' }}>
        <AAPResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.queryByRole('link', { name: /view job template in aap/i })).not.toBeInTheDocument()
  })
})
