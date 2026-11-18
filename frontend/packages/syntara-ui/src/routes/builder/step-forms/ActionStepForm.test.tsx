import { ExecutorTypeEnum } from '@syntara/contracts'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient } from '../../../client'
import { SynForm } from '../../../components/forms/SynForm'
import { useSynForm } from '../../../hooks/useSynForm'
import { useAllProjects, useSelectableProjects } from '../../access/useAllProjects'
import { useExecutionTargetPermissions } from '../../execution-plane/useExecutionTargetPermissions'
import { useAllCredentials } from '../components/useAllCredentials'
import { ScriptAffinityEnum } from '../utils/scriptExecutionProfile'

import { actionFormSchema } from './actionFormSchema'
import { ActionStepForm, HttpUrlField } from './ActionStepForm'
import { renderWithHeader } from './test-utils/renderWithHeader'
import { useAllEnabledExecutionTargets } from './useAllEnabledExecutionTargets'

// Mock credentialsClient used by CredentialSelector (now only for /credential_types
// and the single-credential read-only lookup — the credentials list comes from useAllCredentials)
vi.mock('../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// CredentialSelector fetches its credential list via this hook (see useAllCredentials.test.tsx
// for its own pagination coverage) — mocking it keeps these form tests synchronous.
vi.mock('../components/useAllCredentials', () => ({
  useAllCredentials: vi.fn(),
}))

vi.mock('../../access/useAllProjects', () => ({
  useAllProjects: vi.fn(),
  useSelectableProjects: vi.fn(),
}))

vi.mock('../../execution-plane/useExecutionTargetPermissions', () => ({
  useExecutionTargetPermissions: vi.fn(),
}))

vi.mock('./useAllEnabledExecutionTargets', () => ({
  useAllEnabledExecutionTargets: vi.fn(),
}))

const allowedExecutionTargetPermissions = {
  canRead: true,
  canCreate: true,
  canUpdate: true,
  canDelete: true,
  isLoading: false,
  tooltips: { read: '', create: '', update: '', enable: '', delete: '' },
}

// Mock ExpandableCodeEditor to use a simple textarea for testing
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    ariaLabel,
    language,
  }: {
    code: string
    onCodeChange: (code: string) => void
    ariaLabel?: string
    language: string
  }) => (
    <textarea
      data-testid="code-editor"
      data-language={language}
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
      aria-label={ariaLabel}
      placeholder="Enter your code..."
    />
  ),
}))

describe('ActionStepForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(credentialsClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isPending: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(useAllCredentials).mockReturnValue({
      credentials: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(credentialsClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    })
    vi.mocked(useAllProjects).mockReturnValue({ projects: [], isLoading: false, error: null, refetch: vi.fn() })
    vi.mocked(useSelectableProjects).mockReturnValue({ projects: [], isLoading: false, error: null, refetch: vi.fn() })
    vi.mocked(useExecutionTargetPermissions).mockReturnValue(allowedExecutionTargetPermissions)
    vi.mocked(useAllEnabledExecutionTargets).mockReturnValue({
      targets: [],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
  })

  it('renders script fields by default and hides the action type selector', () => {
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} />)

    expect(screen.queryByLabelText(/Action type/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Language' })).not.toBeInTheDocument()
    expect(screen.getByLabelText(/Script code editor/i)).toBeInTheDocument()
    expect(screen.getByTestId('code-editor')).toHaveAttribute('data-language', 'python')
    expect(screen.queryByRole('textbox', { name: 'URL' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'HTTP Method' })).not.toBeInTheDocument()
  })

  it('requires code for script nodes', async () => {
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} />)

    fireEvent.submit(screen.getByTestId('action-step-form'))

    expect(await screen.findByText('Script code is required')).toBeInTheDocument()
    expect(mockOnSubmit).not.toHaveBeenCalled()
  })

  it('renders API fields when initialData sets executor to api', () => {
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

    expect(screen.queryByLabelText(/Action type/i)).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'URL' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'HTTP Method' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Language' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Script code editor/i)).not.toBeInTheDocument()
  })

  it('populates form with initial data for script executor', () => {
    renderWithHeader(
      <ActionStepForm
        onSubmit={mockOnSubmit}
        initialData={{
          name: 'Existing Script',
          executor: ExecutorTypeEnum.SCRIPT_BASH,
          code: 'echo "hello"',
          parameters: '{"param": "value"}',
        }}
      />
    )

    expect(screen.getByDisplayValue('Existing Script')).toBeInTheDocument()
    expect(screen.getByDisplayValue('echo "hello"')).toBeInTheDocument()
    expect(screen.getByDisplayValue('{"param": "value"}')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Language' })).not.toBeInTheDocument()
    expect(screen.getByTestId('code-editor')).toHaveAttribute('data-language', 'bash')
  })

  it('populates form with initial data for API executor', () => {
    renderWithHeader(
      <ActionStepForm
        onSubmit={mockOnSubmit}
        initialData={{
          name: 'Existing API',
          executor: 'http_request',
          method: 'POST',
          url: 'https://example.com/api',
          headers: [{ id: 'h1', key: 'X-Custom', value: 'header' }],
          body: '{"data": "test"}',
        }}
      />
    )

    expect(screen.getByDisplayValue('Existing API')).toBeInTheDocument()
    expect(screen.getByDisplayValue('https://example.com/api')).toBeInTheDocument()
    expect(screen.getByDisplayValue('X-Custom')).toBeInTheDocument()
    expect(screen.getByDisplayValue('header')).toBeInTheDocument()
    expect(screen.getByDisplayValue('{"data": "test"}')).toBeInTheDocument()
  })

  it.each([ExecutorTypeEnum.SCRIPT_PYTHON, ExecutorTypeEnum.SCRIPT_BASH])(
    'saves execution placement for %s nodes',
    async (executor) => {
      const user = userEvent.setup()
      const targetId = '550e8400-e29b-41d4-a716-446655440000'
      vi.mocked(useAllEnabledExecutionTargets).mockReturnValue({
        targets: [{ id: targetId, name: 'Build worker' }] as never,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor }} />)

      await user.click(screen.getByRole('tab', { name: 'Execution' }))
      await user.click(screen.getByRole('button', { name: 'Affinity' }))
      await user.click(screen.getByRole('option', { name: /Required target/i }))
      await user.click(screen.getByRole('button', { name: 'Execution target' }))
      await user.click(screen.getByRole('option', { name: 'Build worker' }))
      await user.click(screen.getByRole('tab', { name: 'Parameters' }))
      await user.type(screen.getByPlaceholderText(/Enter your code/i), 'print("ready")')
      fireEvent.submit(screen.getByTestId('action-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            executor,
            affinity: ScriptAffinityEnum.REQUIRED_TARGET,
            execution_target_id: targetId,
          })
        )
      })
    }
  )

  it('passes projectId to CredentialSelector for HTTP request executor', () => {
    const useAllCredentialsMock = vi.mocked(useAllCredentials)
    useAllCredentialsMock.mockClear()

    renderWithHeader(
      <ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} projectId="project-123" />
    )

    expect(useAllCredentialsMock).toHaveBeenCalledWith({ projectId: 'project-123' })
  })

  it('validates URL field for API executor', () => {
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

    expect(screen.getByPlaceholderText(/https:\/\/api.example.com/i)).toHaveAttribute('type', 'url')
  })

  it('submits script form data', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} />)

    await user.type(screen.getByPlaceholderText(/Enter your code/i), 'print("hello")')
    fireEvent.submit(screen.getByTestId('action-step-form'))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: '',
          executor: ExecutorTypeEnum.SCRIPT_PYTHON,
          code: 'print("hello")',
        })
      )
    })
  })

  it('submits API form data', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

    await user.type(screen.getByPlaceholderText(/https:\/\/api.example.com/i), 'https://api.test.com/data')
    await user.click(screen.getByRole('button', { name: 'HTTP Method' }))
    await user.click(screen.getByRole('option', { name: 'POST' }))
    fireEvent.submit(screen.getByTestId('action-step-form'))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: '',
          executor: 'http_request',
          method: 'POST',
          url: 'https://api.test.com/data',
        })
      )
    })
  })

  it('submits Bash nodes as a distinct executor with no language parameter', async () => {
    const user = userEvent.setup()
    renderWithHeader(
      <ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: ExecutorTypeEnum.SCRIPT_BASH }} />
    )

    await user.type(screen.getByPlaceholderText(/Enter your code/i), 'echo "test"')
    fireEvent.submit(screen.getByTestId('action-step-form'))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ executor: ExecutorTypeEnum.SCRIPT_BASH, code: 'echo "test"' })
      )
    })
    expect(mockOnSubmit.mock.calls[0][0]).not.toHaveProperty('language')
  })

  it('includes parameters in submission when provided', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} />)

    await user.type(screen.getByPlaceholderText(/Enter your code/i), 'code')
    const paramsInput = screen.getByPlaceholderText('{"MY_VAR": "value"}')
    await user.click(paramsInput)
    await user.paste('{"test": "123"}')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          parameters: '{"test": "123"}',
        })
      )
    })
  })

  it('shows validation error for invalid environment JSON', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} />)

    await user.type(screen.getByPlaceholderText(/Enter your code/i), 'code')
    const paramsInput = screen.getByPlaceholderText('{"MY_VAR": "value"}')
    await user.click(paramsInput)
    await user.paste('not valid json')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => {
      expect(screen.getByText(/Must be a valid JSON object/i)).toBeInTheDocument()
    })
    expect(mockOnSubmit).not.toHaveBeenCalled()
  })

  it('shows validation error for non-string environment values', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} />)

    await user.type(screen.getByPlaceholderText(/Enter your code/i), 'code')
    const paramsInput = screen.getByPlaceholderText('{"MY_VAR": "value"}')
    await user.click(paramsInput)
    await user.paste('{"VAR": 123}')
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => {
      expect(screen.getByText(/Must be a valid JSON object/i)).toBeInTheDocument()
    })
    expect(mockOnSubmit).not.toHaveBeenCalled()
  })

  it('renders code editor with drop support for script executor', () => {
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} />)

    expect(screen.getByTestId('code-editor')).toBeInTheDocument()
  })

  it('accepts drop on environment variables field for script executor', () => {
    renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} />)

    const parametersField = screen.getByRole('textbox', { name: 'Environment variables' })

    fireEvent.drop(parametersField, {
      dataTransfer: {
        getData: (type: string) => {
          if (type === 'application/json') return '{"type":"syntara/input-field"}'
          if (type === 'text/plain') return '${trigger.tier}'
          return ''
        },
      },
    })

    expect(parametersField).toHaveValue('${trigger.tier}')
  })

  it.each([ExecutorTypeEnum.SCRIPT_PYTHON, ExecutorTypeEnum.SCRIPT_BASH])(
    'does not show Developer Preview label for %s executor',
    (executor) => {
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor }} />)
      expect(screen.queryByText('Developer Preview')).not.toBeInTheDocument()
    }
  )

  describe('Secret URL credential — URL field locking', () => {
    const mockSecretUrlType = {
      id: 'type-secret-url',
      name: 'Secret URL',
      description: 'Stores a URL as an encrypted secret',
      inputs: {},
      injectors: {},
      managed: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    const mockSecretUrlCredential = {
      id: 'cred-webhook',
      name: 'Webhook Endpoint — Prod',
      description: 'Production webhook URL',
      credential_type_id: 'type-secret-url',
      enabled: true,
      inputs: {},
      project_id: 'proj-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1', type: 'user' as const },
    }
    const mockBearerType = {
      id: 'type-bearer',
      name: 'HTTP Bearer Token',
      description: 'Bearer token authentication',
      inputs: {},
      injectors: {},
      managed: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    const mockBearerCredential = {
      id: 'cred-bearer',
      name: 'Bearer Token Credential',
      description: null,
      credential_type_id: 'type-bearer',
      enabled: true,
      inputs: {},
      project_id: 'proj-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1', type: 'user' as const },
    }

    // `credentialsClient.useQuery` is still mocked with path-based branching here because
    // HttpCredentialSection (the parent of CredentialSelector for the HTTP executor) makes
    // its own direct '/credentials' + '/credential_types' calls to compute isUrlManagedByCredential —
    // that duplicate fetch is a pre-existing, separate call site untouched by this fix.
    // `useAllCredentials` additionally needs to be mocked so CredentialSelector's own dropdown
    // (rendered inside HttpCredentialSection) shows the same credentials.
    function setupSecretUrlMocks() {
      vi.mocked(credentialsClient.useQuery).mockImplementation(
        (_method: string, path: string): ReturnType<(typeof credentialsClient)['useQuery']> => {
          if (path === '/credential_types') {
            return {
              data: { resources: [mockSecretUrlType] },
              isPending: false,
              isError: false,
              error: null,
              refetch: vi.fn(),
            } as never
          }
          return {
            data: { resources: [mockSecretUrlCredential] },
            isPending: false,
            isError: false,
            error: null,
            refetch: vi.fn(),
          } as never
        }
      )
      vi.mocked(useAllCredentials).mockReturnValue({
        credentials: [mockSecretUrlCredential],
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })
    }

    function setupMixedCredentialMocks() {
      vi.mocked(credentialsClient.useQuery).mockImplementation(
        (_method: string, path: string): ReturnType<(typeof credentialsClient)['useQuery']> => {
          if (path === '/credential_types') {
            return {
              data: { resources: [mockSecretUrlType, mockBearerType] },
              isPending: false,
              isError: false,
              error: null,
              refetch: vi.fn(),
            } as never
          }
          return {
            data: { resources: [mockSecretUrlCredential, mockBearerCredential] },
            isPending: false,
            isError: false,
            error: null,
            refetch: vi.fn(),
          } as never
        }
      )
      vi.mocked(useAllCredentials).mockReturnValue({
        credentials: [mockSecretUrlCredential, mockBearerCredential],
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })
    }

    it('disables URL field and shows locked placeholder when Secret URL credential is selected', async () => {
      const user = userEvent.setup()
      setupSecretUrlMocks()
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))

      const urlInput = screen.getByRole('textbox', { name: 'URL' })
      expect(urlInput).toBeDisabled()
      expect(urlInput).toHaveAttribute('placeholder', 'URL managed by credential')
    })

    it('shows helper text explaining the URL is injected at runtime when Secret URL credential is selected', async () => {
      const user = userEvent.setup()
      setupSecretUrlMocks()
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))

      expect(
        screen.getByText(
          'This value will be injected at execution time and is never stored in the workflow definition.'
        )
      ).toBeInTheDocument()
    })

    it('URL field is not marked required when Secret URL credential is selected', async () => {
      const user = userEvent.setup()
      setupSecretUrlMocks()
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))

      expect(screen.getByRole('textbox', { name: 'URL' })).not.toBeRequired()
    })

    it('URL field is enabled and shows normal placeholder with no credential selected', () => {
      // Uses the default beforeEach mocks (empty credential list)
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      const urlInput = screen.getByRole('textbox', { name: 'URL' })
      expect(urlInput).not.toBeDisabled()
      expect(urlInput).toHaveAttribute('placeholder', 'https://api.example.com/endpoint')
    })

    it('URL field is immediately locked on initial render when initialData includes a Secret URL credential', () => {
      setupSecretUrlMocks()
      renderWithHeader(
        <ActionStepForm
          onSubmit={mockOnSubmit}
          initialData={{ executor: 'http_request', credential_id: 'cred-webhook' }}
        />
      )

      const urlInput = screen.getByRole('textbox', { name: 'URL' })
      expect(urlInput).toBeDisabled()
      expect(urlInput).toHaveAttribute('placeholder', 'URL managed by credential')
    })

    it('submits credential_id in the form payload when Secret URL credential is selected', async () => {
      const user = userEvent.setup()
      setupSecretUrlMocks()
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))
      fireEvent.submit(screen.getByTestId('action-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            executor: 'http_request',
            credential_id: 'cred-webhook',
          })
        )
      })
    })

    it('URL field remains enabled when a non-Secret-URL credential is selected', async () => {
      const user = userEvent.setup()
      vi.mocked(credentialsClient.useQuery).mockImplementation(
        (_method: string, path: string): ReturnType<(typeof credentialsClient)['useQuery']> => {
          if (path === '/credential_types') {
            return {
              data: { resources: [mockBearerType] },
              isPending: false,
              isError: false,
              error: null,
              refetch: vi.fn(),
            } as never
          }
          return {
            data: { resources: [mockBearerCredential] },
            isPending: false,
            isError: false,
            error: null,
            refetch: vi.fn(),
          } as never
        }
      )
      vi.mocked(useAllCredentials).mockReturnValue({
        credentials: [mockBearerCredential],
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Bearer Token Credential/i }))

      const urlInput = screen.getByRole('textbox', { name: 'URL' })
      expect(urlInput).not.toBeDisabled()
      expect(urlInput).toHaveAttribute('placeholder', 'https://api.example.com/endpoint')
    })

    it('URL field re-enables when switching from a Secret URL to a non-Secret-URL credential', async () => {
      const user = userEvent.setup()
      setupMixedCredentialMocks()
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      // Select Secret URL — URL locks
      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))
      expect(screen.getByRole('textbox', { name: 'URL' })).toBeDisabled()

      // Switch to Bearer Token — URL unlocks
      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Bearer Token Credential/i }))
      expect(screen.getByRole('textbox', { name: 'URL' })).not.toBeDisabled()
      expect(screen.getByRole('textbox', { name: 'URL' })).toHaveAttribute(
        'placeholder',
        'https://api.example.com/endpoint'
      )
    })

    it('URL field is locked immediately when loading and credential_id is pre-set', () => {
      // HttpCredentialSection derives isUrlManagedByCredential from its own direct
      // credentialsClient.useQuery('/credentials') + ('/credential_types') calls (a pre-existing,
      // separate call site — see the comment above setupSecretUrlMocks), so it's this mock,
      // not useAllCredentials, that must report the loading state here.
      vi.mocked(credentialsClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })
      renderWithHeader(
        <ActionStepForm
          onSubmit={mockOnSubmit}
          initialData={{ executor: 'http_request', credential_id: 'cred-webhook' }}
        />
      )
      expect(screen.getByRole('textbox', { name: 'URL' })).toBeDisabled()
    })

    it('clears the URL value when a Secret URL credential is selected after typing a URL', async () => {
      const user = userEvent.setup()
      setupSecretUrlMocks()
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.type(screen.getByRole('textbox', { name: 'URL' }), 'https://old.example.com')
      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))

      expect(screen.getByRole('textbox', { name: 'URL' })).toHaveValue('')
    })

    it('has no accessibility violations in the locked URL state (HttpUrlField in isolation)', async () => {
      // Render HttpUrlField directly — avoids the PatternFly tab aria-controls/id
      // mismatch that occurs in happy-dom when testing the full ActionStepForm.
      function Wrapper() {
        const form = useSynForm({
          schema: actionFormSchema,
          defaultValues: { name: '', executor: 'http_request', url: '', settings: {} },
        })
        return (
          <form>
            <SynForm form={form}>
              <HttpUrlField isUrlManagedByCredential isDisabled={false} />
            </SynForm>
          </form>
        )
      }
      const { container } = render(<Wrapper />)
      expect(await axe(container)).toHaveNoViolations()
    })
  })

  describe('retry policy visibility', () => {
    it('hides retry policy for script executor', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: ExecutorTypeEnum.SCRIPT_PYTHON }} />
      )

      await user.click(screen.getByRole('tab', { name: 'Settings' }))

      expect(screen.queryByRole('switch', { name: 'Override retry policy' })).not.toBeInTheDocument()
    })

    it('shows retry policy for HTTP request executor', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ActionStepForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('tab', { name: 'Settings' }))

      expect(screen.getByRole('switch', { name: 'Override retry policy' })).toBeInTheDocument()
    })

    it('omits script settings that contain only the unsupported retry policy', async () => {
      renderWithHeader(
        <ActionStepForm
          onSubmit={mockOnSubmit}
          initialData={{
            executor: ExecutorTypeEnum.SCRIPT_PYTHON,
            code: 'print("hello")',
            settings: { retry_policy: { max_retries: 3, initial_interval: 10 } },
          }}
        />
      )

      fireEvent.submit(screen.getByTestId('action-step-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            executor: ExecutorTypeEnum.SCRIPT_PYTHON,
            settings: undefined,
          })
        )
      })
    })
  })
})
