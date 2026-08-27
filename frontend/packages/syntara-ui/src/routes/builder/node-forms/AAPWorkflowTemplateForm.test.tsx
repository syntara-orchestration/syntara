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
      id="aap-wf-extraVars"
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
      onBlur={(e) => onBlur?.(e.currentTarget.value)}
      placeholder='{"version": "1.0", "environment": "prod"}'
      aria-label={ariaLabel}
    />
  ),
}))

import type { AAPWorkflowTemplateDetail } from '../../../hooks/useAAPBrowser'
import { submitForm } from '../../../test/submit-form'
import { useAllCredentials } from '../components/useAllCredentials'

import { AAPWorkflowTemplateForm } from './AAPWorkflowTemplateForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

// Mock useAAPBrowser hook to provide test data without real API calls
const mockRetryAll = vi.fn()

const defaultWorkflowTemplateDetail: AAPWorkflowTemplateDetail = {
  id: 20,
  name: 'Deploy Workflow',
  description: 'Deploy application workflow',
  ask_inventory_on_launch: false,
  ask_variables_on_launch: true,
  ask_limit_on_launch: true,
  ask_scm_branch_on_launch: true,
  ask_labels_on_launch: false,
  ask_tags_on_launch: true,
  ask_skip_tags_on_launch: true,
  survey_enabled: false,
  url: 'https://aap.example.com/execution/templates/workflow-job-template/20/details',
  // Default values from template configuration
  default_inventory: { id: 1, name: 'Demo Inventory' },
  default_labels: [],
}

// Base mock data shared across all tests (static data that doesn't change)
const baseMockAAPBrowserData = {
  organizations: [
    { id: 1, name: 'Default' },
    { id: 2, name: 'Engineering' },
  ],
  workflowTemplates: [
    { id: 20, name: 'Deploy Workflow', description: 'Deploy application workflow', organization_name: 'Default' },
    { id: 21, name: 'Backup Workflow', description: 'Backup database workflow', organization_name: 'Default' },
  ],
  inventories: [{ id: 1, name: 'Demo Inventory', description: 'Demo hosts', organization_name: 'Default' }],
  labels: [],
  selectedOrg: '',
  selectOrganization: vi.fn(),
  selectTemplate: vi.fn(),
  resetAll: vi.fn(),
  loadingOrgs: false,
  loadingTemplates: false,
  loadingInventories: false,
  loadingLabels: false,
  loadingTemplateDetail: false,
  workflowTemplateDetail: undefined,
  error: null,
  retryAll: mockRetryAll,
  searchOrganizations: vi.fn(),
  searchTemplates: vi.fn(),
  searchInventories: vi.fn(),
  searchLabels: vi.fn(),
}

// Helper function to create mock return value with a specific workflow template detail
function createMockAAPBrowser(workflowTemplateDetail: AAPWorkflowTemplateDetail) {
  return {
    ...baseMockAAPBrowserData,
    workflowTemplateDetail,
  }
}

describe('AAPWorkflowTemplateForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    mockUseAAPBrowser.mockClear()
    mockOnSubmit.mockClear()
    // Set default mock implementation (can be overridden in nested describe blocks)
    mockUseAAPBrowser.mockReturnValue(createMockAAPBrowser(defaultWorkflowTemplateDetail))

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
      <AAPWorkflowTemplateForm onSubmit={mockOnSubmit} onCancel={vi.fn()} initialData={{ integration_id: 'int-123' }} />
    )

    expect(screen.getByLabelText(/Name/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Select an organization/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Select a workflow template/i)).toBeInTheDocument()
    // AAPCredentialStatus renders when an integration is selected
    expect(screen.getByText(/Set up connection/i)).toBeInTheDocument()
  })

  it('renders credential selector', () => {
    renderWithHeader(
      <AAPWorkflowTemplateForm onSubmit={mockOnSubmit} onCancel={vi.fn()} initialData={{ integration_id: 'int-123' }} />
    )

    // AAPCredentialStatus renders when an integration is selected
    expect(screen.getByText(/Set up connection/i)).toBeInTheDocument()
  })

  it('renders workflow template typeahead even when no organization is selected', () => {
    renderWithHeader(<AAPWorkflowTemplateForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    const templateInput = screen.getByPlaceholderText(/Select a workflow template/i)
    expect(templateInput).toBeInTheDocument()
  })

  it('submits form even without organization selected (permissive schema)', async () => {
    const user = userEvent.setup()
    renderWithHeader(<AAPWorkflowTemplateForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Test Workflow')

    await submitForm()

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Test Workflow',
        })
      )
    })
  })

  it('populates form with initial data', () => {
    renderWithHeader(
      <AAPWorkflowTemplateForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        initialData={{
          name: 'Existing Workflow',
          organization_name: 'Default',
          workflow_job_template_name: 'Deploy Workflow',
          workflow_job_template_id: 20,
          limit: 'webservers',
        }}
      />
    )

    expect(screen.getByDisplayValue('Existing Workflow')).toBeInTheDocument()
    // Typeahead shows selected value in the input when closed
    expect(screen.getByDisplayValue('Default')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Deploy Workflow')).toBeInTheDocument()
  })

  it('passes projectId to CredentialSelector', async () => {
    const user = userEvent.setup()
    const useAllCredentialsMock = vi.mocked(useAllCredentials)
    useAllCredentialsMock.mockClear()

    renderWithHeader(
      <AAPWorkflowTemplateForm
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

  it('renders prompt on launch fields based on workflow template detail flags', () => {
    renderWithHeader(<AAPWorkflowTemplateForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

    // Fields enabled in defaultWorkflowTemplateDetail should be visible
    expect(screen.getByLabelText('Extra Variables')).toBeInTheDocument()
    expect(screen.getByLabelText('Limit')).toBeInTheDocument()
    expect(screen.getByLabelText('Source control branch')).toBeInTheDocument()
    expect(screen.getByLabelText('Job tags')).toBeInTheDocument()
    expect(screen.getByLabelText('Skip tags')).toBeInTheDocument()

    // Fields disabled in defaultWorkflowTemplateDetail should NOT be visible
    expect(screen.queryByPlaceholderText(/Use default inventory/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Labels/i)).not.toBeInTheDocument()
  })

  it('renders form with all prompt-on-launch initial values', () => {
    // Renders form with comprehensive initial data to exercise code paths
    renderWithHeader(
      <AAPWorkflowTemplateForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        initialData={{
          organization_name: 'Default',
          workflow_job_template_name: 'Deploy Workflow',
          workflow_job_template_id: 20,
          inventory_name: 'Production',
          inventory_id: 1,
          extra_vars: '{"key": "value"}',
          limit: 'host1',
          scm_branch: 'main',
          tags: 'deploy',
          skip_tags: 'debug',
          labels: ['prod'],
        }}
      />
    )

    // Verify form rendered with organization and template
    expect(screen.getByPlaceholderText(/Select an organization/i)).toHaveValue('Default')
    expect(screen.getByPlaceholderText(/Select a workflow template/i)).toHaveValue('Deploy Workflow')
  })

  it('clears downstream values when organization changes', async () => {
    const user = userEvent.setup()
    renderWithHeader(
      <AAPWorkflowTemplateForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        initialData={{
          organization_name: 'Default',
          workflow_job_template_name: 'Deploy Workflow',
          workflow_job_template_id: 20,
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

    // Verify organization changed and template was cleared
    await waitFor(() => {
      expect(orgInput).toHaveValue('Engineering')
    })

    const templateInput = screen.getByPlaceholderText(/Select a workflow template/i)
    expect(templateInput).toHaveValue('')
  })

  it('clears downstream values when template changes', async () => {
    const user = userEvent.setup()
    renderWithHeader(
      <AAPWorkflowTemplateForm
        onSubmit={mockOnSubmit}
        onCancel={vi.fn()}
        initialData={{
          organization_name: 'Default',
          workflow_job_template_name: 'Deploy Workflow',
          workflow_job_template_id: 20,
          name: 'Test Step',
        }}
      />
    )

    // Click the template field to open dropdown
    const templateInput = screen.getByPlaceholderText(/Select a workflow template/i)
    await user.click(templateInput)

    // Find and click a template option from the dropdown
    const backupOption = await screen.findByText('Backup Workflow')
    await user.click(backupOption)

    // Verify template changed (the onChange handler clears prompt-on-launch fields internally)
    await waitFor(() => {
      expect(templateInput).toHaveValue('Backup Workflow')
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = renderWithHeader(<AAPWorkflowTemplateForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

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
    const templateWithPrompts: AAPWorkflowTemplateDetail = {
      ...defaultWorkflowTemplateDetail,
      ask_inventory_on_launch: true,
      ask_labels_on_launch: true,
    }

    beforeEach(() => {
      // Use template with prompt flags enabled for these tests
      mockUseAAPBrowser.mockReturnValue(createMockAAPBrowser(templateWithPrompts))
    })

    it('handles workflow template with no default values gracefully', async () => {
      // Create a template with no defaults (overrides the beforeEach mock for this test)
      const templateWithNoDefaults: AAPWorkflowTemplateDetail = {
        ...templateWithPrompts,
        default_inventory: null,
        default_labels: [],
      }
      mockUseAAPBrowser.mockReturnValue(createMockAAPBrowser(templateWithNoDefaults))

      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            organization_name: 'Default',
            workflow_job_template_name: 'Deploy Workflow',
            workflow_job_template_id: 20,
          }}
        />
      )

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /parameters/i })).toBeInTheDocument()
      })

      // Should show "No default" placeholders
      expect(screen.getByPlaceholderText(/No default inventory/i)).toBeInTheDocument()
    })
  })

  describe('Form Submission', () => {
    it('submits form with pre-filled required fields including integration_id', async () => {
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            name: 'Test Workflow',
            organization_name: 'Default',
            workflow_job_template_name: 'Deploy Workflow',
            workflow_job_template_id: 20,
            integration_id: 'int-123',
          }}
        />
      )

      await submitForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Test Workflow',
            organization_name: 'Default',
            workflow_job_template_name: 'Deploy Workflow',
            workflow_job_template_id: 20,
            integration_id: 'int-123',
          })
        )
      })
    })
  })

  describe('Expression Mode', () => {
    it('toggles expression mode switch', async () => {
      const user = userEvent.setup()
      renderWithHeader(<AAPWorkflowTemplateForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      const expressionSwitch = screen.getByRole('switch', { name: 'Use input variables' })
      expect(expressionSwitch).not.toBeChecked()

      await user.click(expressionSwitch)

      expect(expressionSwitch).toBeChecked()
    })

    it('shows expression text fields when expression mode is enabled', async () => {
      const user = userEvent.setup()
      renderWithHeader(<AAPWorkflowTemplateForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      const expressionSwitch = screen.getByRole('switch', { name: 'Use input variables' })
      await user.click(expressionSwitch)

      // Expression mode fields should appear
      expect(screen.getByPlaceholderText(/org name or drag expression/i)).toBeInTheDocument()
      expect(screen.getByPlaceholderText(/template name or drag expression/i)).toBeInTheDocument()
      expect(screen.getByPlaceholderText(/inventory name or drag expression/i)).toBeInTheDocument()
      expect(screen.getByPlaceholderText(/branch name or drag expression/i)).toBeInTheDocument()
    })

    it('auto-detects expression mode from initial data', () => {
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            organization_name: '${workflow.context.org}',
            workflow_job_template_name: 'Deploy Workflow',
          }}
        />
      )

      const expressionSwitch = screen.getByRole('switch', { name: 'Use input variables' })
      expect(expressionSwitch).toBeChecked()
    })

    it('auto-detects expression mode from workflow_job_template_name expression', () => {
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            organization_name: 'Default',
            workflow_job_template_name: '${workflow.context.template}',
          }}
        />
      )

      const expressionSwitch = screen.getByRole('switch', { name: 'Use input variables' })
      expect(expressionSwitch).toBeChecked()
    })

    it('auto-detects expression mode from inventory_name expression', () => {
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            inventory_name: '${workflow.context.inventory}',
          }}
        />
      )

      const expressionSwitch = screen.getByRole('switch', { name: 'Use input variables' })
      expect(expressionSwitch).toBeChecked()
    })

    it('auto-detects expression mode from limit expression', () => {
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            limit: '${workflow.context.limit}',
          }}
        />
      )

      const expressionSwitch = screen.getByRole('switch', { name: 'Use input variables' })
      expect(expressionSwitch).toBeChecked()
    })

    it('auto-detects expression mode from scm_branch expression', () => {
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            scm_branch: '${workflow.context.branch}',
          }}
        />
      )

      const expressionSwitch = screen.getByRole('switch', { name: 'Use input variables' })
      expect(expressionSwitch).toBeChecked()
    })

    it('does not auto-detect expression mode when no fields contain expressions', () => {
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            organization_name: 'Default',
            workflow_job_template_name: 'Deploy Workflow',
            inventory_name: 'prod',
            limit: 'webservers',
            scm_branch: 'main',
          }}
        />
      )

      const expressionSwitch = screen.getByRole('switch', { name: 'Use input variables' })
      expect(expressionSwitch).not.toBeChecked()
    })
  })
})
