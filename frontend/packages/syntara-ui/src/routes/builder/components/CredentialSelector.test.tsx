import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient } from '../../../client'
import { FieldHelpPopover } from '../../../components/FieldHelpPopover'
import type { Credential } from '../../configuration/credentials/credentialConstants'

import { CredentialSelector, type CredentialSelectorProps } from './CredentialSelector'
import { useAllCredentials } from './useAllCredentials'

vi.mock('../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// `useAllCredentials` owns the paginated fetch (see useAllCredentials.test.tsx for its own
// async/pagination coverage). Mocking it here keeps CredentialSelector's tests synchronous,
// exactly like they were before it fetched all pages instead of a single page.
vi.mock('./useAllCredentials', () => ({
  useAllCredentials: vi.fn(),
}))

vi.mock('../../configuration/credentials/form/CredentialFormModal', () => ({
  CredentialFormModal: ({
    isOpen,
    onClose,
    onCreated,
    preSelectedTypeId,
    defaultProjectId,
  }: {
    isOpen: boolean
    onClose: () => void
    onCreated?: (id: string) => void
    preSelectedTypeId?: string
    defaultProjectId?: string
  }) =>
    isOpen ? (
      <div
        data-testid="credential-form-modal"
        data-pre-selected-type-id={preSelectedTypeId}
        data-default-project-id={defaultProjectId}
      >
        <button onClick={onClose}>Close modal</button>
        <button onClick={() => onCreated?.('new-cred-id')}>Simulate create</button>
      </div>
    ) : null,
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const mockCredentials = [
  {
    id: 'cred-1',
    name: 'Production API Key',
    description: 'API key for production',
    credential_type_id: 'type-1',
    enabled: true,
    inputs: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    created_by: 'user-1',
  },
  {
    id: 'cred-2',
    name: 'Staging Token',
    description: null,
    credential_type_id: 'type-2',
    enabled: true,
    inputs: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    created_by: 'user-1',
  },
  {
    id: 'cred-3',
    name: 'Dev Bearer Token',
    description: 'Bearer token for dev environment',
    credential_type_id: 'type-1',
    enabled: true,
    inputs: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    created_by: 'user-1',
  },
]

const mockCredentialTypes = [
  {
    id: 'type-1',
    name: 'HTTP Bearer Token',
    description: 'Bearer token authentication',
    inputs: {},
    injectors: {},
    managed: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'type-2',
    name: 'HTTP Basic Auth',
    description: 'Basic authentication',
    inputs: {},
    injectors: {},
    managed: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'type-3',
    name: 'Secret URL',
    description: 'Stores a URL as an encrypted secret',
    inputs: {},
    injectors: {},
    managed: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

type CredentialsListOverride = {
  data?: { resources?: Record<string, unknown>[] }
  isPending?: boolean
}

function mockUseQuery(
  overrides: {
    credentials?: CredentialsListOverride
    credentialTypes?: Record<string, unknown>
    singleCredential?: Record<string, unknown> | null
  } = {}
) {
  // `data` is intentionally checked with `in` (not `??`) so that passing `data: undefined`
  // (the loading-state shape used throughout this file) is distinguishable from omitting it.
  const credentialsOverride = overrides.credentials ?? {}
  const listData = 'data' in credentialsOverride ? credentialsOverride.data : { resources: mockCredentials }
  vi.mocked(useAllCredentials).mockReturnValue({
    credentials: (listData?.resources ?? []) as Credential[],
    isLoading: credentialsOverride.isPending ?? false,
    error: null,
    refetch: vi.fn() as unknown as ReturnType<typeof useAllCredentials>['refetch'],
  })

  const typesResponse = {
    data: { resources: mockCredentialTypes },
    isPending: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
    ...overrides.credentialTypes,
  }
  const singleCredResponse =
    overrides.singleCredential !== undefined
      ? { data: overrides.singleCredential, isPending: false, error: null }
      : { data: null, isPending: false, error: null }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  vi.mocked(credentialsClient.useQuery).mockImplementation((_method: string, path: string): any => {
    if (path === '/credentials/{credential_id}') {
      return singleCredResponse
    }
    return typesResponse
  })
}

/** Legacy mock helper for tests that don't need grouped display */
function mockUseQueryLegacy(overrides: CredentialsListOverride = {}) {
  mockUseQuery({
    credentials: overrides,
    credentialTypes: { data: { resources: [] } },
  })
}

function renderSelector(props: Partial<CredentialSelectorProps> = {}) {
  const defaultProps: CredentialSelectorProps = {
    onChange: vi.fn(),
    ...props,
  }
  return render(<CredentialSelector {...defaultProps} />, { wrapper })
}

describe('CredentialSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders with no selection and default placeholder', () => {
    mockUseQueryLegacy()
    renderSelector()

    expect(screen.getByRole('button', { name: 'Credential' })).toHaveTextContent('Select a credential...')
  })

  it('renders with custom placeholder', () => {
    mockUseQueryLegacy()
    renderSelector({ placeholder: 'Pick one' })

    expect(screen.getByRole('button', { name: 'Credential' })).toHaveTextContent('Pick one')
  })

  it('renders selected credential name', () => {
    mockUseQueryLegacy()
    renderSelector({ value: 'cred-1' })

    expect(screen.getByRole('button', { name: 'Credential' })).toHaveTextContent('Production API Key')
  })

  it('renders the form group label', () => {
    mockUseQueryLegacy()
    renderSelector({ label: 'API Credential' })

    expect(screen.getByText('API Credential')).toBeInTheDocument()
  })

  it('shows dropdown with credential list when clicked', async () => {
    const user = userEvent.setup()
    mockUseQueryLegacy()
    renderSelector()

    await user.click(screen.getByRole('button', { name: 'Credential' }))

    expect(screen.getByText('Production API Key')).toBeInTheDocument()
    expect(screen.getByText('Staging Token')).toBeInTheDocument()
    expect(screen.getByText('Dev Bearer Token')).toBeInTheDocument()
  })

  it('opens a menu with many credential options', async () => {
    const user = userEvent.setup()
    const manyCredentials = Array.from({ length: 20 }, (_, i) => ({
      id: `cred-${i + 1}`,
      name: `Credential ${i + 1}`,
      description: null,
      credential_type_id: 'type-1',
      enabled: true,
      inputs: {},
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      created_by: 'user-1',
    }))
    mockUseQueryLegacy({ data: { resources: manyCredentials } })
    renderSelector()

    await user.click(screen.getByRole('button', { name: 'Credential' }))

    expect(screen.getByRole('listbox', { name: 'Credential options' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Credential 1' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Credential 20' })).toBeInTheDocument()
  })

  it('calls onChange with credential ID when selecting a credential', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    mockUseQueryLegacy()
    renderSelector({ onChange })

    await user.click(screen.getByRole('button', { name: 'Credential' }))
    await user.click(screen.getByRole('option', { name: /Production API Key/ }))

    expect(onChange).toHaveBeenCalledWith('cred-1')
  })

  it('shows loading state', () => {
    mockUseQueryLegacy({ data: undefined, isPending: true })
    renderSelector()

    expect(screen.getByLabelText('Loading credentials')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Credential' })).toHaveTextContent('Loading credentials...')
  })

  it('disables toggle while loading', () => {
    mockUseQueryLegacy({ data: undefined, isPending: true })
    renderSelector()

    expect(screen.getByRole('button', { name: 'Credential' })).toBeDisabled()
  })

  it('shows empty state when no credentials available', async () => {
    const user = userEvent.setup()
    mockUseQueryLegacy({ data: { resources: [] } })
    renderSelector()

    await user.click(screen.getByRole('button', { name: 'Credential' }))

    expect(screen.getByText('No credentials available')).toBeInTheDocument()
  })

  it('disables toggle when isDisabled is true', () => {
    mockUseQueryLegacy()
    renderSelector({ isDisabled: true })

    expect(screen.getByRole('button', { name: 'Credential' })).toBeDisabled()
  })

  it('always fetches all credentials without type filter (filtering happens client-side)', () => {
    mockUseQuery()
    renderSelector({ compatibleTypeNames: ['HTTP Bearer Token'] })

    expect(useAllCredentials).toHaveBeenCalledWith({ projectId: undefined })
  })

  it('filters credentials client-side by compatible type names', async () => {
    const user = userEvent.setup()
    mockUseQuery()
    renderSelector({ compatibleTypeNames: ['HTTP Bearer Token'] })

    await user.click(screen.getByRole('button', { name: 'Credential' }))

    // type-1 credentials should be visible
    expect(screen.getByText('Production API Key')).toBeInTheDocument()
    expect(screen.getByText('Dev Bearer Token')).toBeInTheDocument()
    // type-2 credential should be filtered out
    expect(screen.queryByText('Staging Token')).not.toBeInTheDocument()
  })

  it('shows all credentials when compatibleTypeNames is not provided', async () => {
    const user = userEvent.setup()
    mockUseQuery()
    renderSelector()

    await user.click(screen.getByRole('button', { name: 'Credential' }))

    expect(screen.getByText('Production API Key')).toBeInTheDocument()
    expect(screen.getByText('Staging Token')).toBeInTheDocument()
    expect(screen.getByText('Dev Bearer Token')).toBeInTheDocument()
  })

  it('shows selected credential name on toggle after selection', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    mockUseQueryLegacy()
    renderSelector({ onChange })

    await user.click(screen.getByRole('button', { name: 'Credential' }))
    await user.click(screen.getByRole('option', { name: /Staging Token/ }))

    expect(onChange).toHaveBeenCalledWith('cred-2')
  })

  it('has no accessibility violations with credentials loaded', async () => {
    mockUseQueryLegacy()
    const { container } = renderSelector()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with dropdown open', async () => {
    const user = userEvent.setup()
    mockUseQueryLegacy()
    const { container } = renderSelector()

    await user.click(screen.getByRole('button', { name: 'Credential' }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations in loading state', async () => {
    mockUseQueryLegacy({ data: undefined, isPending: true })
    const { container } = renderSelector()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('projectId filtering', () => {
    it('passes projectId through to useAllCredentials when provided', () => {
      mockUseQuery()
      renderSelector({ projectId: 'proj-123' })

      expect(useAllCredentials).toHaveBeenCalledWith({ projectId: 'proj-123' })
    })

    it('passes projectId as undefined to useAllCredentials when not provided', () => {
      mockUseQuery()
      renderSelector()

      expect(useAllCredentials).toHaveBeenCalledWith({ projectId: undefined })
    })

    it('has no accessibility violations when projectId is provided', async () => {
      mockUseQuery()
      const { container } = renderSelector({ projectId: 'proj-123' })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('grouped display by credential type', () => {
    it('groups credentials by type with group headers when types are available', async () => {
      const user = userEvent.setup()
      mockUseQuery()
      renderSelector()

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      // Group headers should be visible
      expect(screen.getByText('HTTP BEARER TOKEN')).toBeInTheDocument()
      expect(screen.getByText('HTTP BASIC AUTH')).toBeInTheDocument()
    })

    it('renders credentials under their type group', async () => {
      const user = userEvent.setup()
      mockUseQuery()
      renderSelector()

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      // All credentials still visible
      expect(screen.getByText('Production API Key')).toBeInTheDocument()
      expect(screen.getByText('Dev Bearer Token')).toBeInTheDocument()
      expect(screen.getByText('Staging Token')).toBeInTheDocument()
    })

    it('renders ungrouped when no credential types are available', async () => {
      const user = userEvent.setup()
      mockUseQuery({ credentialTypes: { data: { resources: [] } } })
      renderSelector()

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      // Credentials visible without group headers
      expect(screen.getByText('Production API Key')).toBeInTheDocument()
      expect(screen.queryByText('HTTP BEARER TOKEN')).not.toBeInTheDocument()
    })

    it('fetches credential types from the API', () => {
      mockUseQuery()
      renderSelector()

      expect(credentialsClient.useQuery).toHaveBeenCalledWith('get', '/credential_types')
    })
  })

  describe('helpText popover', () => {
    it('renders help icon when helpText is provided', () => {
      mockUseQueryLegacy()
      renderSelector({ helpText: 'Some help text', label: 'My Credential' })

      expect(screen.getByRole('button', { name: 'More info for My Credential' })).toBeInTheDocument()
    })

    it('does not render help icon when helpText is not provided', () => {
      mockUseQueryLegacy()
      renderSelector({ label: 'My Credential' })

      expect(screen.queryByRole('button', { name: /More info/i })).not.toBeInTheDocument()
    })

    it('shows popover content when help icon is clicked', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({ helpText: 'This is help content', label: 'My Credential' })

      await user.click(screen.getByRole('button', { name: 'More info for My Credential' }))

      expect(screen.getByText('This is help content')).toBeInTheDocument()
    })

    it('prefers an explicit labelHelp element over helpText', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({
        label: 'My Credential',
        helpText: 'Should not appear',
        labelHelp: <FieldHelpPopover headerContent="My Credential" helpText="Explicit label help" />,
      })

      await user.click(screen.getByRole('button', { name: 'More info for My Credential' }))
      expect(screen.getByText('Explicit label help')).toBeInTheDocument()
      expect(screen.queryByText('Should not appear')).not.toBeInTheDocument()
    })
  })

  describe('inline credential creation', () => {
    it('shows "Create new credential" option when allowCreate is true', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({ allowCreate: true })

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      expect(screen.getByRole('option', { name: 'Create new credential' })).toBeInTheDocument()
    })

    it('renders "Create new credential" before credential groups in dropdown', async () => {
      const user = userEvent.setup()
      mockUseQuery()
      renderSelector({ allowCreate: true })

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      const options = screen.getAllByRole('option')
      const createIndex = options.findIndex((o) => o.textContent?.includes('Create new credential'))
      const firstCredentialIndex = options.findIndex((o) => o.textContent?.includes('Production API Key'))

      expect(createIndex).toBeGreaterThan(-1)
      expect(firstCredentialIndex).toBeGreaterThan(-1)
      expect(createIndex).toBeLessThan(firstCredentialIndex)
    })

    it('does not show "Create new credential" option when allowCreate is false', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({ allowCreate: false })

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      expect(screen.queryByRole('option', { name: 'Create new credential' })).not.toBeInTheDocument()
    })

    it('opens the create modal when "Create new credential" is clicked', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({ allowCreate: true })

      await user.click(screen.getByRole('button', { name: 'Credential' }))
      await user.click(screen.getByRole('option', { name: 'Create new credential' }))

      expect(screen.getByTestId('credential-form-modal')).toBeInTheDocument()
    })

    it('passes preSelectedTypeId to the create modal', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({ allowCreate: true, preSelectedTypeId: 'type-bearer' })

      await user.click(screen.getByRole('button', { name: 'Credential' }))
      await user.click(screen.getByRole('option', { name: 'Create new credential' }))

      expect(screen.getByTestId('credential-form-modal')).toHaveAttribute('data-pre-selected-type-id', 'type-bearer')
    })

    it('passes projectId as defaultProjectId to the create modal', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({ allowCreate: true, projectId: 'proj-123' })

      await user.click(screen.getByRole('button', { name: 'Credential' }))
      await user.click(screen.getByRole('option', { name: 'Create new credential' }))

      expect(screen.getByTestId('credential-form-modal')).toHaveAttribute('data-default-project-id', 'proj-123')
    })

    it('auto-selects the new credential after creation', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      mockUseQueryLegacy()
      renderSelector({ allowCreate: true, onChange })

      // Open dropdown and click create
      await user.click(screen.getByRole('button', { name: 'Credential' }))
      await user.click(screen.getByRole('option', { name: 'Create new credential' }))

      // Simulate successful creation
      await user.click(screen.getByText('Simulate create'))

      expect(onChange).toHaveBeenCalledWith('new-cred-id')
    })

    it('passes a different projectId as defaultProjectId to the create modal', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({ allowCreate: true, projectId: 'proj-456' })

      await user.click(screen.getByRole('button', { name: 'Credential' }))
      await user.click(screen.getByRole('option', { name: 'Create new credential' }))

      expect(screen.getByTestId('credential-form-modal')).toHaveAttribute('data-default-project-id', 'proj-456')
    })

    it('does not lock credential type when multiple compatible types exist', async () => {
      const user = userEvent.setup()
      mockUseQuery()
      renderSelector({
        allowCreate: true,
        compatibleTypeNames: ['HTTP Bearer Token', 'HTTP Basic Auth'],
      })

      await user.click(screen.getByRole('button', { name: 'Credential' }))
      await user.click(screen.getByRole('option', { name: 'Create new credential' }))

      const modal = screen.getByTestId('credential-form-modal')
      expect(modal).not.toHaveAttribute('data-pre-selected-type-id')
    })

    it('locks credential type when exactly one compatible type exists', async () => {
      const user = userEvent.setup()
      mockUseQuery()
      renderSelector({
        allowCreate: true,
        compatibleTypeNames: ['HTTP Bearer Token'],
      })

      await user.click(screen.getByRole('button', { name: 'Credential' }))
      await user.click(screen.getByRole('option', { name: 'Create new credential' }))

      expect(screen.getByTestId('credential-form-modal')).toHaveAttribute('data-pre-selected-type-id', 'type-1')
    })

    it('does not show "No credentials available" when allowCreate is true and list is empty', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy({ data: { resources: [] } })
      renderSelector({ allowCreate: true })

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      expect(screen.queryByText('No credentials available')).not.toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Create new credential' })).toBeInTheDocument()
    })
  })

  describe('no credential option', () => {
    it('shows "No credential" option in the dropdown when isRequired is false', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector()

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      expect(screen.getByRole('option', { name: /No credential/ })).toBeInTheDocument()
    })

    it('calls onChange with undefined when "No credential" is selected', async () => {
      const user = userEvent.setup()
      const onChange = vi.fn()
      mockUseQueryLegacy()
      renderSelector({ value: 'cred-1', onChange })

      await user.click(screen.getByRole('button', { name: 'Credential' }))
      await user.click(screen.getByRole('option', { name: /No credential/ }))

      expect(onChange).toHaveBeenCalledWith(undefined)
    })

    it('does not show "No credential" option when isRequired is true', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      renderSelector({ isRequired: true })

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      expect(screen.queryByRole('option', { name: /No credential/ })).not.toBeInTheDocument()
    })

    it('has no accessibility violations with "No credential" option visible', async () => {
      const user = userEvent.setup()
      mockUseQueryLegacy()
      const { container } = renderSelector()

      await user.click(screen.getByRole('button', { name: 'Credential' }))

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('read-only credential (credential:use denied)', () => {
    const readOnlyCred = {
      id: 'cred-readonly',
      name: 'Restricted Prod Cred',
      credential_type_id: 'type-1',
      enabled: true,
    }

    function mockReadOnlyState() {
      // Usable credentials list is empty (user has no credential:use)
      // but a single credential fetch returns the credential (user has credential:read)
      mockUseQuery({
        credentials: { data: { resources: [] } },
        singleCredential: readOnlyCred,
      })
    }

    it('shows credential name with "(no permission to use)" when value is not in usable list', () => {
      mockReadOnlyState()
      renderSelector({ value: 'cred-readonly' })

      expect(screen.getByRole('button', { name: 'Credential' })).toHaveTextContent(
        'Restricted Prod Cred (no permission to use)'
      )
    })

    it('disables the toggle when user can read but not use the credential', () => {
      mockReadOnlyState()
      renderSelector({ value: 'cred-readonly' })

      expect(screen.getByRole('button', { name: 'Credential' })).toHaveAttribute(
        'aria-describedby',
        'credential-readonly-warning'
      )
    })

    it('shows warning helper text when credential is read-only', () => {
      mockReadOnlyState()
      renderSelector({ value: 'cred-readonly' })

      expect(screen.getByText(/You do not have permission to use this credential/)).toBeInTheDocument()
    })

    it('fetches the single credential by ID when value is not in usable list', () => {
      mockReadOnlyState()
      renderSelector({ value: 'cred-readonly' })

      expect(credentialsClient.useQuery).toHaveBeenCalledWith(
        'get',
        '/credentials/{credential_id}',
        { params: { path: { credential_id: 'cred-readonly' } } },
        expect.objectContaining({ enabled: true })
      )
    })

    it('has no accessibility violations in read-only credential state', async () => {
      mockReadOnlyState()
      const { container } = renderSelector({ value: 'cred-readonly' })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('does not show warning when credential is in the usable list', () => {
      mockUseQuery({ singleCredential: null })
      renderSelector({ value: 'cred-1' })

      expect(screen.queryByText(/You do not have permission to use this credential/)).not.toBeInTheDocument()
    })
  })
})
