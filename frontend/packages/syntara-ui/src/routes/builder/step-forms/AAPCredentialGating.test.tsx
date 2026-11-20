// Credential-gating regression coverage for AAP resource browsing.
//
// These tests render the real AAPJobTemplateForm / AAPWorkflowTemplateForm with
// the real useAAPBrowser hook. Only the AAP query client is stubbed, and the
// stub honors the production `enabled` flag: resource data is returned only
// when the hook actually enables the query. This proves the credential gate in
// production code — not the stub — is what keeps organizations and templates
// out of the dropdowns before a credential is selected.
//
// IMPORTANT: vi.mock() calls are hoisted by Vitest and execute before imports
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Controllable stub for the AAP proxy query client; deferred reference so it
// resolves after hoisting (see vi.mock hoisting rules).
const mockAapUseQuery = vi.fn()

vi.mock('../../../client', () => ({
  aapClient: {
    useQuery: (...args: unknown[]) => mockAapUseQuery(...args) as unknown,
  },
  credentialsClient: {
    useQuery: vi.fn(() => ({
      data: undefined,
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

// CredentialSelector fetches its credential list via this hook — mocking it
// keeps these tests synchronous. Two credentials let tests switch between
// them to exercise the selection reconciliation.
vi.mock('../components/useAllCredentials', () => ({
  useAllCredentials: vi.fn(() => ({
    credentials: [
      {
        id: 'cred-1',
        name: 'Credential One',
        credential_type_id: 'type-aap',
        description: 'First test credential for AAP',
        project_id: 'proj-1',
        enabled: true,
      },
      {
        id: 'cred-2',
        name: 'Credential Two',
        credential_type_id: 'type-aap',
        description: 'Second test credential for AAP',
        project_id: 'proj-1',
        enabled: true,
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
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
      onBlur={(e) => onBlur?.(e.currentTarget.value)}
      aria-label={ariaLabel}
    />
  ),
}))

import { AAPJobTemplateForm } from './AAPJobTemplateForm'
import { AAPWorkflowTemplateForm } from './AAPWorkflowTemplateForm'
import { AAP_CREDENTIAL_REQUIRED_HINT } from './shared/stepFieldHelpText'
import { renderWithHeader } from './test-utils/renderWithHeader'

/**
 * Resource pages the stub returns for each AAP proxy list endpoint. Only
 * served when the production hook enables the query.
 */
const AAP_RESOURCES: Record<string, { results: Array<{ id: number; name: string; description?: string }> }> = {
  '/proxies/aap/organizations': {
    results: [
      { id: 1, name: 'Default' },
      { id: 2, name: 'Engineering' },
    ],
  },
  '/proxies/aap/job_templates': {
    results: [{ id: 10, name: 'Deploy App', description: 'Deploy the application' }],
  },
  '/proxies/aap/workflow_job_templates': {
    results: [{ id: 20, name: 'Deploy Workflow', description: 'Deploy application workflow' }],
  },
  '/proxies/aap/inventories': { results: [] },
  '/proxies/aap/execution_environments': { results: [] },
  '/proxies/aap/credentials': { results: [] },
  '/proxies/aap/instance_groups': { results: [] },
  '/proxies/aap/labels': { results: [] },
}

/**
 * Per-credential resource pages, keyed `${credential_id}:${path}`. Unset
 * entries fall back to the shared pages above — what a credential with full
 * access would see. Tests install pages to simulate a credential that lost
 * access to specific resources.
 */
const credentialResources = new Map<string, { results: Array<{ id: number; name: string; description?: string }> }>()

/** Serve a credential-specific resource page from the query stub. */
function stubCredentialResource(
  credentialId: string,
  path: string,
  page: { results: Array<{ id: number; name: string; description?: string }> }
) {
  credentialResources.set(`${credentialId}:${path}`, page)
}

/** Disabled queries must look idle with no data, exactly like a real one. */
const idleQuery = {
  data: undefined,
  isPending: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
}

function stubAapQuery() {
  mockAapUseQuery.mockImplementation(
    (_method: unknown, path: unknown, config: unknown, options?: { enabled?: boolean }) => {
      if (options?.enabled === false) {
        return { ...idleQuery, refetch: vi.fn() }
      }
      const credentialId = (config as { params?: { query?: { credential_id?: string } } } | undefined)?.params?.query
        ?.credential_id
      const page = credentialResources.get(`${credentialId ?? ''}:${path as string}`) ?? AAP_RESOURCES[path as string]
      return {
        data: page,
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }
    }
  )
}

/** Open a typeahead dropdown by clicking its filter input. */
async function openDropdown(user: ReturnType<typeof userEvent.setup>, placeholder: string) {
  await user.click(screen.getByPlaceholderText(placeholder))
}

/** Close any open dropdown so the next one opens cleanly. */
async function closeDropdown(user: ReturnType<typeof userEvent.setup>) {
  await user.keyboard('{Escape}')
}

/**
 * Switch the node credential through the inline credential picker. The picker
 * renders inline because the mocked credentials client cannot resolve the
 * selected credential's name.
 */
async function switchCredential(user: ReturnType<typeof userEvent.setup>, credentialName: string) {
  await user.click(screen.getByRole('button', { name: /Credential (One|Two)/ }))
  // Regex match: the option's accessible name includes its description
  await user.click(screen.getByRole('option', { name: new RegExp(credentialName) }))
}

describe('AAP credential gating', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    credentialResources.clear()
    stubAapQuery()
  })

  describe('AAPJobTemplateForm', () => {
    it('does not offer organizations or job templates before a credential is selected', async () => {
      const user = userEvent.setup()
      renderWithHeader(<AAPJobTemplateForm onSubmit={vi.fn()} initialData={{ integration_id: 'int-123' }} />)

      await openDropdown(user, 'Select an organization')
      expect(screen.queryByRole('option', { name: /Default/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('option', { name: /Engineering/ })).not.toBeInTheDocument()
      await closeDropdown(user)

      await openDropdown(user, 'Select a job template')
      expect(screen.queryByRole('option', { name: /Deploy App/ })).not.toBeInTheDocument()
      await closeDropdown(user)

      expect(screen.getByText(AAP_CREDENTIAL_REQUIRED_HINT)).toBeInTheDocument()
    })

    it('offers organizations and job templates after a credential is selected', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <AAPJobTemplateForm onSubmit={vi.fn()} initialData={{ integration_id: 'int-123', credential_id: 'cred-1' }} />
      )

      await openDropdown(user, 'Select an organization')
      expect(await screen.findByRole('option', { name: /Default/ })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Engineering/ })).toBeInTheDocument()
      await closeDropdown(user)

      await openDropdown(user, 'Select a job template')
      expect(await screen.findByRole('option', { name: /Deploy App/ })).toBeInTheDocument()
    })

    it('stops offering resources after the credential is cleared', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <AAPJobTemplateForm onSubmit={vi.fn()} initialData={{ integration_id: 'int-123', credential_id: 'cred-1' }} />
      )

      await openDropdown(user, 'Select an organization')
      expect(await screen.findByRole('option', { name: /Default/ })).toBeInTheDocument()
      await closeDropdown(user)

      // Clear the credential through the picker rendered by AAPCredentialStatus
      await user.click(screen.getByRole('button', { name: /Credential One/ }))
      await user.click(screen.getByRole('option', { name: 'No credential' }))

      await openDropdown(user, 'Select an organization')
      expect(screen.queryByRole('option', { name: /Default/ })).not.toBeInTheDocument()
    })

    it('retains selections the new credential can still access', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <AAPJobTemplateForm
          onSubmit={vi.fn()}
          initialData={{
            integration_id: 'int-123',
            credential_id: 'cred-1',
            organization_name: 'Default',
            job_template_name: 'Deploy App',
            job_template_id: 10,
          }}
        />
      )

      const orgInput = screen.getByPlaceholderText('Select an organization')
      const templateInput = screen.getByPlaceholderText('Select a job template')
      expect(orgInput).toHaveValue('Default')
      expect(templateInput).toHaveValue('Deploy App')

      await switchCredential(user, 'Credential Two')

      // Both resources remain visible under the new credential
      expect(orgInput).toHaveValue('Default')
      expect(templateInput).toHaveValue('Deploy App')
    })

    it('clears organization and template when the new credential loses the organization', async () => {
      const user = userEvent.setup()
      stubCredentialResource('cred-2', '/proxies/aap/organizations', {
        results: [{ id: 3, name: 'Other Org' }],
      })
      renderWithHeader(
        <AAPJobTemplateForm
          onSubmit={vi.fn()}
          initialData={{
            integration_id: 'int-123',
            credential_id: 'cred-1',
            organization_name: 'Default',
            job_template_name: 'Deploy App',
            job_template_id: 10,
          }}
        />
      )

      const orgInput = screen.getByPlaceholderText('Select an organization')
      const templateInput = screen.getByPlaceholderText('Select a job template')
      expect(orgInput).toHaveValue('Default')

      await switchCredential(user, 'Credential Two')

      expect(orgInput).toHaveValue('')
      expect(templateInput).toHaveValue('')

      // The browser stops tracking the cleared template: its detail query is disabled
      const detailCalls = mockAapUseQuery.mock.calls.filter(
        (c: unknown[]) => c[1] === '/proxies/aap/job_templates/{job_template_id}'
      )
      const lastDetailCall = detailCalls.at(-1)
      expect(lastDetailCall).toBeDefined()
      expect(lastDetailCall?.[3]).toMatchObject({ enabled: false })
    })

    it('clears only the template when the new credential keeps the organization', async () => {
      const user = userEvent.setup()
      stubCredentialResource('cred-2', '/proxies/aap/job_templates', {
        results: [{ id: 12, name: 'Other Template', description: 'A different template' }],
      })
      renderWithHeader(
        <AAPJobTemplateForm
          onSubmit={vi.fn()}
          initialData={{
            integration_id: 'int-123',
            credential_id: 'cred-1',
            organization_name: 'Default',
            job_template_name: 'Deploy App',
            job_template_id: 10,
          }}
        />
      )

      const orgInput = screen.getByPlaceholderText('Select an organization')
      const templateInput = screen.getByPlaceholderText('Select a job template')
      expect(orgInput).toHaveValue('Default')
      expect(templateInput).toHaveValue('Deploy App')

      await switchCredential(user, 'Credential Two')

      expect(orgInput).toHaveValue('Default')
      expect(templateInput).toHaveValue('')
    })
  })

  describe('AAPWorkflowTemplateForm', () => {
    it('does not offer organizations or workflow templates before a credential is selected', async () => {
      const user = userEvent.setup()
      renderWithHeader(<AAPWorkflowTemplateForm onSubmit={vi.fn()} initialData={{ integration_id: 'int-123' }} />)

      await openDropdown(user, 'Select an organization')
      expect(screen.queryByRole('option', { name: /Default/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('option', { name: /Engineering/ })).not.toBeInTheDocument()
      await closeDropdown(user)

      await openDropdown(user, 'Select a workflow template')
      expect(screen.queryByRole('option', { name: /Deploy Workflow/ })).not.toBeInTheDocument()
      await closeDropdown(user)

      expect(screen.getByText(AAP_CREDENTIAL_REQUIRED_HINT)).toBeInTheDocument()
    })

    it('offers organizations and workflow templates after a credential is selected', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={vi.fn()}
          initialData={{ integration_id: 'int-123', credential_id: 'cred-1' }}
        />
      )

      await openDropdown(user, 'Select an organization')
      expect(await screen.findByRole('option', { name: /Default/ })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /Engineering/ })).toBeInTheDocument()
      await closeDropdown(user)

      await openDropdown(user, 'Select a workflow template')
      expect(await screen.findByRole('option', { name: /Deploy Workflow/ })).toBeInTheDocument()
    })

    it('clears organization and workflow template when the new credential loses the organization', async () => {
      const user = userEvent.setup()
      stubCredentialResource('cred-2', '/proxies/aap/organizations', {
        results: [{ id: 3, name: 'Other Org' }],
      })
      renderWithHeader(
        <AAPWorkflowTemplateForm
          onSubmit={vi.fn()}
          initialData={{
            integration_id: 'int-123',
            credential_id: 'cred-1',
            organization_name: 'Default',
            workflow_job_template_name: 'Deploy Workflow',
            workflow_job_template_id: 20,
          }}
        />
      )

      const orgInput = screen.getByPlaceholderText('Select an organization')
      const templateInput = screen.getByPlaceholderText('Select a workflow template')
      expect(orgInput).toHaveValue('Default')
      expect(templateInput).toHaveValue('Deploy Workflow')

      await switchCredential(user, 'Credential Two')

      expect(orgInput).toHaveValue('')
      expect(templateInput).toHaveValue('')

      // The browser stops tracking the cleared template: its detail query is disabled
      const detailCalls = mockAapUseQuery.mock.calls.filter(
        (c: unknown[]) => c[1] === '/proxies/aap/workflow_job_templates/{workflow_job_template_id}'
      )
      const lastDetailCall = detailCalls.at(-1)
      expect(lastDetailCall).toBeDefined()
      expect(lastDetailCall?.[3]).toMatchObject({ enabled: false })
    })
  })
})
