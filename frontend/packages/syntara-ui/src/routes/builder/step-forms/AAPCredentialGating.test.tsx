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
// keeps these tests synchronous.
vi.mock('../components/useAllCredentials', () => ({
  useAllCredentials: vi.fn(() => ({
    credentials: [
      {
        id: 'cred-1',
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
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
      onBlur={(e) => onBlur?.(e.currentTarget.value)}
      aria-label={ariaLabel}
    />
  ),
}))

import { AAPJobTemplateForm } from './AAPJobTemplateForm'
import { AAPWorkflowTemplateForm } from './AAPWorkflowTemplateForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

const CREDENTIAL_REQUIRED_HINT = 'Select a credential to browse resources'

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
    (_method: unknown, path: unknown, _config: unknown, options?: { enabled?: boolean }) => {
      if (options?.enabled === false) {
        return { ...idleQuery, refetch: vi.fn() }
      }
      return {
        data: AAP_RESOURCES[path as string],
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

describe('AAP credential gating', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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

      expect(screen.getByText(CREDENTIAL_REQUIRED_HINT)).toBeInTheDocument()
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
      await user.click(screen.getByRole('button', { name: /Test AAP Credential/ }))
      await user.click(screen.getByRole('option', { name: 'No credential' }))

      await openDropdown(user, 'Select an organization')
      expect(screen.queryByRole('option', { name: /Default/ })).not.toBeInTheDocument()
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

      expect(screen.getByText(CREDENTIAL_REQUIRED_HINT)).toBeInTheDocument()
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
  })
})
