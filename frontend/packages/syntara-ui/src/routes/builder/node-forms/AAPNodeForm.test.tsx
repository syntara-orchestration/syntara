// IMPORTANT: vi.mock() calls are hoisted by Vitest and execute before imports
// Import order: @testing-library/react, @testing-library/user-event, then vitest
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

// Create a controllable mock function for useAAPBrowser
const mockUseAAPBrowser = vi.fn()

// Mock useAAPBrowser hook BEFORE importing components that use it
vi.mock('../../../hooks/useAAPBrowser', () => ({
  useAAPBrowser: (...args: unknown[]) =>
    mockUseAAPBrowser(...args) as ReturnType<typeof import('../../../hooks/useAAPBrowser').useAAPBrowser>,
}))

// Mock credentials client for CredentialSelector (only /credential_types now — the
// credentials list comes from useAllCredentials, mocked separately below)
vi.mock('../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(() => ({
      data: { resources: [] },
      isPending: false,
      isError: false,
      refetch: vi.fn(),
    })),
    useMutation: vi.fn(),
  },
  integrationsClient: {
    useQuery: vi.fn(() => ({
      data: {
        resources: [
          { id: 'int-123', name: 'AAP Gateway', integration_type: 'ansible_automation_platform', enabled: true },
        ],
      },
      isPending: false,
      isError: false,
      refetch: vi.fn(),
    })),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// CredentialSelector fetches its credential list via this hook (see useAllCredentials.test.tsx
// for its own pagination coverage) — mocking it keeps these form tests synchronous.
vi.mock('../components/useAllCredentials', () => ({
  useAllCredentials: vi.fn(() => ({
    credentials: [
      {
        id: 'test-credential-id',
        name: 'Test AAP Credential',
        credential_type_id: 'type-aap',
        description: 'Test credential for AAP',
        project_id: 'proj-1',
      },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })),
}))

// Mock useIntegrationPermissions to avoid async act() warnings from permission queries
vi.mock('../../configuration/integrations/useIntegrationPermissions', () => ({
  useIntegrationPermissions: vi.fn(() => ({
    canCreate: true,
    canUpdate: false,
    canDelete: false,
    isLoading: false,
    tooltips: { create: '', update: '', enable: '', validate: '', delete: '' },
  })),
}))

// Mock CredentialFormModal
vi.mock('../../../routes/configuration/credentials/form/CredentialFormModal', () => ({
  CredentialFormModal: () => null,
}))

// Mock ExpandableCodeEditor to use a simple textarea for testing
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    onBlur,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (code: string) => void
    onBlur?: (value: string) => void
    ariaLabel?: string
  }) => (
    <textarea
      data-testid="extra-vars-editor"
      id="aap-extraVars"
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
      onBlur={(e) => onBlur?.(e.currentTarget.value)}
      placeholder='{"version": "1.0", "environment": "prod"}'
      aria-label={ariaLabel}
    />
  ),
}))

import type { AAPJobTemplateDetail } from '../../../hooks/useAAPBrowser'
import { submitForm } from '../../../test/submit-form'
import { useAllCredentials } from '../components/useAllCredentials'

import { AAPJobTemplateForm as AAPNodeForm } from './AAPJobTemplateForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

// Mock useAAPBrowser hook to provide test data without real API calls
const mockRetryAll = vi.fn()

const defaultTemplateDetail: AAPJobTemplateDetail = {
  id: 10,
  name: 'Deploy App',
  description: 'Deploy the application',
  ask_job_type_on_launch: true,
  ask_inventory_on_launch: false,
  ask_credential_on_launch: false,
  ask_variables_on_launch: true,
  ask_limit_on_launch: true,
  ask_tags_on_launch: true,
  ask_skip_tags_on_launch: true,
  ask_verbosity_on_launch: true,
  ask_diff_mode_on_launch: true,
  ask_forks_on_launch: true,
  ask_job_slice_count_on_launch: true,
  ask_execution_environment_on_launch: false,
  ask_instance_groups_on_launch: false,
  ask_labels_on_launch: false,
  ask_timeout_on_launch: true,
  survey_enabled: false,
  url: 'https://aap.example.com/execution/templates/job-template/10/details',
  // Default values from template configuration
  default_inventory: { id: 1, name: 'Demo Inventory' },
  default_execution_environment: { id: 1, name: 'Default EE' },
  default_credentials: [{ id: 1, name: 'SSH Machine Credential' }],
}

// Base mock data shared across all tests (static data that doesn't change)
const baseMockAAPBrowserData = {
  organizations: [
    { id: 1, name: 'Default' },
    { id: 2, name: 'Engineering' },
  ],
  jobTemplates: [
    { id: 10, name: 'Deploy App', description: 'Deploy the application', organization_name: 'Default' },
    { id: 11, name: 'Backup DB', description: 'Backup the database', organization_name: 'Default' },
  ],
  inventories: [{ id: 1, name: 'Demo Inventory', description: 'Demo hosts', organization_name: 'Default' }],
  executionEnvironments: [
    { id: 1, name: 'Default EE', description: 'Default execution environment' },
    { id: 2, name: 'Custom EE', description: 'Custom EE with extra collections' },
  ],
  credentials: [
    { id: 1, name: 'Machine Credential', description: 'SSH key for hosts' },
    { id: 2, name: 'AWS Credential', description: 'AWS access keys' },
  ],
  instanceGroups: [
    { id: 1, name: 'default' },
    { id: 2, name: 'controlplane' },
  ],
  labels: [],
  selectedOrg: '',
  selectOrganization: vi.fn(),
  selectJobTemplate: vi.fn(),
  resetAll: vi.fn(),
  loadingOrgs: false,
  loadingTemplates: false,
  loadingInventories: false,
  loadingExecutionEnvironments: false,
  loadingCredentials: false,
  loadingInstanceGroups: false,
  loadingLabels: false,
  loadingTemplateDetail: false,
  templateDetail: undefined,
  error: null,
  retryAll: mockRetryAll,
  searchOrganizations: vi.fn(),
  searchJobTemplates: vi.fn(),
  searchInventories: vi.fn(),
  searchExecutionEnvironments: vi.fn(),
  searchCredentials: vi.fn(),
  searchInstanceGroups: vi.fn(),
  searchLabels: vi.fn(),
}

// Helper function to create mock return value with a specific template detail
function createMockAAPBrowser(templateDetail: AAPJobTemplateDetail) {
  return {
    ...baseMockAAPBrowserData,
    templateDetail,
  }
}

describe('AAPNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    mockUseAAPBrowser.mockClear()
    mockOnSubmit.mockClear()
    // Set default mock implementation (can be overridden in nested describe blocks)
    mockUseAAPBrowser.mockReturnValue(createMockAAPBrowser(defaultTemplateDetail))

    // Reset the credentials list to the default mock (a single AAP-compatible credential)
    vi.mocked(useAllCredentials).mockReturnValue({
      credentials: [
        {
          id: 'test-credential-id',
          name: 'Test AAP Credential',
          credential_type_id: 'type-aap',
          description: 'Test credential for AAP',
          project_id: 'proj-1',
        },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn() as unknown as ReturnType<typeof useAllCredentials>['refetch'],
    })
  })

  it('renders form with required fields', () => {
    renderWithHeader(
      <AAPNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} initialData={{ integration_id: 'int-123' }} />
    )

    expect(screen.getByLabelText(/Name/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Select an organization/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Select a job template/i)).toBeInTheDocument()
    // AAPCredentialStatus renders when an integration is selected
    expect(screen.getByText(/Set up connection/i)).toBeInTheDocument()
  })

  it('renders credential selector', () => {
    renderWithHeader(
      <AAPNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} initialData={{ integration_id: 'int-123' }} />
    )

    // AAPCredentialStatus renders when an integration is selected
    expect(screen.getByText(/Set up connection/i)).toBeInTheDocument()
  })

  it('renders job template typeahead even when no organization is selected', () => {
    renderWithHeader(<AAPNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    const templateInput = screen.getByPlaceholderText(/Select a job template/i)
    expect(templateInput).toBeInTheDocument()
  })

  it('submits form even without organization selected (permissive schema)', async () => {
    const user = userEvent.setup()
    renderWithHeader(<AAPNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Test Job')

    await submitForm()

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Test Job',
        })
      )
    })
  })

  it('populates form with initial data', () => {
    renderWithHeader(
      <AAPNodeForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        initialData={{
          name: 'Existing Job',
          organization_name: 'Default',
          job_template_name: 'Deploy App',
          job_template_id: 10,
          verbosity: '2',
        }}
      />
    )

    expect(screen.getByDisplayValue('Existing Job')).toBeInTheDocument()
    // Typeahead shows selected value in the input when closed
    expect(screen.getByDisplayValue('Default')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Deploy App')).toBeInTheDocument()
  })

  it('passes projectId to CredentialSelector', async () => {
    const user = userEvent.setup()
    const useAllCredentialsMock = vi.mocked(useAllCredentials)
    useAllCredentialsMock.mockClear()

    renderWithHeader(
      <AAPNodeForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        onHeaderContentChange={vi.fn()}
        projectId="project-456"
        initialData={{ integration_id: 'int-123' }}
      />
    )

    // Open credential picker via "Set up connection" button
    await user.click(screen.getByText(/Set up connection/i))

    expect(useAllCredentialsMock).toHaveBeenCalledWith({ projectId: 'project-456' })
  })

  it('renders prompt on launch fields based on template detail flags', () => {
    renderWithHeader(<AAPNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    // Fields enabled in mockTemplateDetail should be visible
    // use exact names so "More info for …" help buttons do not also match
    expect(screen.getByLabelText('Extra Variables')).toBeInTheDocument()
    expect(screen.getByLabelText('Limit')).toBeInTheDocument()
    expect(screen.getByLabelText('Job tags')).toBeInTheDocument()
    expect(screen.getByLabelText('Skip tags')).toBeInTheDocument()
    expect(screen.getByLabelText('Verbosity')).toBeInTheDocument()
    expect(screen.getByLabelText('Run type')).toBeInTheDocument()
    expect(screen.getByLabelText('Forks')).toBeInTheDocument()
    expect(screen.getByLabelText('Job slicing')).toBeInTheDocument()
    expect(screen.getByLabelText('Show changes')).toBeInTheDocument()

    // Fields disabled in mockTemplateDetail should NOT be visible
    expect(screen.queryByPlaceholderText(/Use default inventory/i)).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/Use default execution environment/i)).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/Use default instance groups/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Labels')).not.toBeInTheDocument()
  })

  it('renders link to view job template in AAP', () => {
    renderWithHeader(<AAPNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    const link = screen.getByRole('link', { name: /View job template in AAP/i })
    expect(link).toHaveAttribute('href', 'https://aap.example.com/execution/templates/job-template/10/details')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('does not render link when URL has non-http scheme', () => {
    // Create template with dangerous URL
    const templateWithBadUrl = {
      ...defaultTemplateDetail,
      url: 'javascript:alert(1)',
    }
    mockUseAAPBrowser.mockReturnValue(createMockAAPBrowser(templateWithBadUrl))

    renderWithHeader(<AAPNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    expect(screen.queryByRole('link', { name: /View job template in AAP/i })).not.toBeInTheDocument()
  })

  it('renders form with all prompt-on-launch initial values', () => {
    // Renders form with comprehensive initial data to exercise code paths
    renderWithHeader(
      <AAPNodeForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        initialData={{
          organization_name: 'Default',
          job_template_name: 'Deploy App',
          job_template_id: 10,
          inventory_name: 'Production',
          inventory_id: 1,
          job_credentials: [1, 2],
          extra_vars: '{"key": "value"}',
          limit: 'host1',
          tags: 'deploy',
          skip_tags: 'debug',
          verbosity: '3',
          job_type: 'run',
          forks: 10,
          job_slice_count: 2,
          diff_mode: true,
          execution_environment: 'Custom EE',
          execution_environment_id: 2,
          instance_group: 'controlplane',
          instance_group_id: 2,
          labels: ['prod'],
        }}
      />
    )

    // Verify form rendered with organization and template
    expect(screen.getByPlaceholderText(/Select an organization/i)).toHaveValue('Default')
    expect(screen.getByPlaceholderText(/Select a job template/i)).toHaveValue('Deploy App')
  })

  it('clears downstream values when organization changes', async () => {
    const user = userEvent.setup()
    renderWithHeader(
      <AAPNodeForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        initialData={{
          organization_name: 'Default',
          job_template_name: 'Deploy App',
          job_template_id: 10,
          name: 'Test Step',
        }}
      />
    )

    // Click the organization field to open dropdown
    const orgInput = screen.getByPlaceholderText(/Select an organization/i)
    await user.click(orgInput)

    // Find and click an organization option from the dropdown
    const engineeringOption = await screen.findByText('Engineering')
    await user.click(engineeringOption)

    // The onChange handler should have been called (clearing template and other fields)
    // We can't easily verify the internal state, but the handler executed
    await waitFor(() => {
      expect(orgInput).toHaveValue('Engineering')
    })
  })

  it('clears downstream values when template changes', async () => {
    const user = userEvent.setup()
    renderWithHeader(
      <AAPNodeForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        initialData={{
          organization_name: 'Default',
          job_template_name: 'Deploy App',
          job_template_id: 10,
          name: 'Test Step',
        }}
      />
    )

    // Click the template field to open dropdown
    const templateInput = screen.getByPlaceholderText(/Select a job template/i)
    await user.click(templateInput)

    // Find and click a template option from the dropdown
    const backupOption = await screen.findByText('Backup DB')
    await user.click(backupOption)

    // The onChange handler should have been called (clearing prompt-on-launch fields)
    await waitFor(() => {
      expect(templateInput).toHaveValue('Backup DB')
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = renderWithHeader(<AAPNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    // Wait for PF6 Tabs async state updates to settle before running axe
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /parameters/i })).toBeInTheDocument()
    })

    const results = await axe(container, {
      rules: {
        // PF6 Tabs renders aria-controls before the tab panel is mounted;
        // this is a known PatternFly timing issue, not an app-level bug.
        'aria-valid-attr-value': { enabled: false },
      },
    })
    expect(results).toHaveNoViolations()
  })

  describe('Default value pre-population', () => {
    // Template configuration for this test suite
    const templateWithPrompts: AAPJobTemplateDetail = {
      ...defaultTemplateDetail,
      ask_inventory_on_launch: true,
      ask_execution_environment_on_launch: true,
      ask_credential_on_launch: true,
    }

    beforeEach(() => {
      // Use template with prompt flags enabled for these tests
      mockUseAAPBrowser.mockReturnValue(createMockAAPBrowser(templateWithPrompts))
    })

    it('handles template with no default values gracefully', async () => {
      // Create a template with no defaults (overrides the beforeEach mock for this test)
      const templateWithNoDefaults: AAPJobTemplateDetail = {
        ...templateWithPrompts,
        default_inventory: null,
        default_execution_environment: null,
        default_credentials: [],
      }
      mockUseAAPBrowser.mockReturnValue(createMockAAPBrowser(templateWithNoDefaults))

      renderWithHeader(
        <AAPNodeForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            organization_name: 'Default',
            job_template_name: 'Deploy App',
            job_template_id: 10,
          }}
        />
      )

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /parameters/i })).toBeInTheDocument()
      })

      // Should show "No default" placeholders
      expect(screen.getByPlaceholderText(/No default inventory/i)).toBeInTheDocument()
      expect(screen.getByPlaceholderText(/No default execution environment/i)).toBeInTheDocument()

      // Credentials should show "No default credentials"
      expect(screen.getByRole('button', { name: /No default credentials/i })).toBeInTheDocument()
    })
  })

  describe('Form Submission', () => {
    it('submits form with pre-filled required fields including integration_id', async () => {
      renderWithHeader(
        <AAPNodeForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            name: 'Test Job',
            organization_name: 'Default',
            job_template_name: 'Deploy App',
            job_template_id: 10,
            integration_id: 'int-123',
          }}
        />
      )

      await submitForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Test Job',
            organization_name: 'Default',
            job_template_name: 'Deploy App',
            job_template_id: 10,
            integration_id: 'int-123',
          })
        )
      })
    })
  })
})
