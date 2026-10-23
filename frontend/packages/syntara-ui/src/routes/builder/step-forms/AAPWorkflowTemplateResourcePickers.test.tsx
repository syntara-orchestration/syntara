import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { useAAPBrowser } from '../../../hooks/useAAPBrowser'

import { AAPWorkflowTemplateResourcePickers } from './AAPWorkflowTemplateResourcePickers'
import type { AAPWorkflowTemplateFormData } from './aapWorkflowTemplateSchema'

// Mock dependencies
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
    <div data-testid={`typeahead-${ariaLabel.toLowerCase().replace(/\s+/g, '-')}`}>
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

vi.mock('./shared/AAPErrorAlert', () => ({
  AAPErrorAlert: ({ error, onRetry }: { error: Error | null; onRetry: () => void }) =>
    error ? (
      <div data-testid="error-alert">
        <p>{error.message}</p>
        <button onClick={onRetry}>Retry</button>
      </div>
    ) : null,
}))

function TestWrapper({
  children,
  defaultValues,
}: {
  children: React.ReactNode
  defaultValues?: Partial<AAPWorkflowTemplateFormData>
}) {
  const methods = useForm<AAPWorkflowTemplateFormData>({
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
    workflowTemplates: [
      { id: 1, name: 'Workflow Template 1', description: 'Workflow description 1' },
      { id: 2, name: 'Workflow Template 2', description: null },
    ],
    selectOrganization: vi.fn(),
    selectTemplate: vi.fn(),
    searchOrganizations: vi.fn(),
    searchTemplates: vi.fn(),
    loadingOrgs: false,
    loadingTemplates: false,
    error: null,
    retryAll: vi.fn(),
    workflowTemplateDetail: undefined,
    ...overrides,
  } as unknown as ReturnType<typeof useAAPBrowser>
}

describe('AAPWorkflowTemplateResourcePickers', () => {
  it('renders organization selector with options', () => {
    const browser = createMockBrowser()
    render(
      <TestWrapper>
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Organization')).toBeInTheDocument()
    expect(screen.getByText('Org 1')).toBeInTheDocument()
    expect(screen.getByText('Org 2')).toBeInTheDocument()
  })

  it('renders workflow template selector with options', () => {
    const browser = createMockBrowser()
    render(
      <TestWrapper>
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Workflow template')).toBeInTheDocument()
    expect(screen.getByText('Workflow Template 1')).toBeInTheDocument()
    expect(screen.getByText('Workflow Template 2')).toBeInTheDocument()
  })

  it('calls selectOrganization when organization is selected', async () => {
    const user = userEvent.setup()
    const browser = createMockBrowser()
    render(
      <TestWrapper>
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    await user.click(screen.getByText('Org 1'))

    expect(browser.selectOrganization).toHaveBeenCalledWith('Org 1')
  })

  it('calls selectTemplate when workflow template is selected', async () => {
    const user = userEvent.setup()
    const browser = createMockBrowser()
    render(
      <TestWrapper>
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    await user.click(screen.getByText('Workflow Template 1'))

    expect(browser.selectTemplate).toHaveBeenCalledWith(1)
  })

  it('shows error state via AAPErrorAlert', () => {
    const error = new Error('Failed to load workflow templates')
    const browser = createMockBrowser({ error })
    render(
      <TestWrapper>
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.getByTestId('error-alert')).toBeInTheDocument()
    expect(screen.getByText('Failed to load workflow templates')).toBeInTheDocument()
  })

  it('calls retryAll when retry button is clicked in error state', async () => {
    const user = userEvent.setup()
    const error = new Error('Connection failed')
    const browser = createMockBrowser({ error })
    render(
      <TestWrapper>
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    await user.click(screen.getByText('Retry'))

    expect(browser.retryAll).toHaveBeenCalled()
  })

  it('displays AAP link when workflow template is selected and has valid URL', () => {
    const browser = createMockBrowser({
      workflowTemplateDetail: {
        id: 1,
        name: 'Workflow Template 1',
        url: 'https://aap.example.com/workflows/1',
      },
    })
    render(
      <TestWrapper
        defaultValues={{
          workflow_job_template_id: 1,
        }}
      >
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    const link = screen.getByRole('link', { name: /view workflow template in aap/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'https://aap.example.com/workflows/1')
  })

  it('does not display AAP link when workflow template URL is invalid', () => {
    const browser = createMockBrowser({
      workflowTemplateDetail: {
        id: 1,
        name: 'Workflow Template 1',
        url: 'invalid-url',
      },
    })
    render(
      <TestWrapper
        defaultValues={{
          workflow_job_template_id: 1,
        }}
      >
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(screen.queryByRole('link', { name: /view workflow template in aap/i })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const browser = createMockBrowser()
    const { container } = render(
      <TestWrapper>
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const error = new Error('Test error')
    const browser = createMockBrowser({ error })
    const { container } = render(
      <TestWrapper>
        <AAPWorkflowTemplateResourcePickers browser={browser} />
      </TestWrapper>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
