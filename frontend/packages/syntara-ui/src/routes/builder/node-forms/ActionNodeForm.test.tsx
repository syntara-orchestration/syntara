import { render, fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient } from '../../../client'
import { useAllProjects, useSelectableProjects } from '../../access/useAllProjects'

import type { ActionFormValues } from './actionFormSchema'
import { ActionNodeForm, HttpUrlField } from './ActionNodeForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

// Mock credentialsClient used by CredentialSelector
vi.mock('../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/useAllProjects', () => ({
  useAllProjects: vi.fn(),
  useSelectableProjects: vi.fn(),
}))

// Mock ExpandableCodeEditor to use a simple textarea for testing
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (code: string) => void
    ariaLabel?: string
  }) => (
    <textarea
      data-testid="code-editor"
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
      aria-label={ariaLabel}
      placeholder="Enter your code..."
    />
  ),
}))

describe('ActionNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(credentialsClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isPending: false,
      error: null,
      refetch: vi.fn(),
    } as never)
    vi.mocked(credentialsClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)
    vi.mocked(useAllProjects).mockReturnValue({ projects: [], isLoading: false, error: null, refetch: vi.fn() })
    vi.mocked(useSelectableProjects).mockReturnValue({ projects: [], isLoading: false, error: null, refetch: vi.fn() })
  })

  it('renders script fields by default and hides the action type selector', () => {
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

    expect(screen.queryByLabelText(/Action type/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Language' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Script code editor/i)).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'URL' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'HTTP Method' })).not.toBeInTheDocument()
  })

  it('submits form even with empty script (permissive schema)', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

    await user.type(screen.getByPlaceholderText(/Enter activity name/i), 'Test Script')
    fireEvent.submit(screen.getByTestId('action-node-form'))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Test Script',
          executor: 'script',
        })
      )
    })
  })

  it('renders API fields when initialData sets executor to api', () => {
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

    expect(screen.queryByLabelText(/Action type/i)).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'URL' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'HTTP Method' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Language' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Script code editor/i)).not.toBeInTheDocument()
  })

  it('populates form with initial data for script executor', () => {
    renderWithHeader(
      <ActionNodeForm
        onSubmit={mockOnSubmit}
        initialData={{
          name: 'Existing Script',
          executor: 'script',
          language: 'bash',
          code: 'echo "hello"',
          parameters: '{"param": "value"}',
        }}
      />
    )

    expect(screen.getByDisplayValue('Existing Script')).toBeInTheDocument()
    expect(screen.getByDisplayValue('echo "hello"')).toBeInTheDocument()
    expect(screen.getByDisplayValue('{"param": "value"}')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Language' })).toHaveTextContent('Bash')
  })

  it('populates form with initial data for API executor', () => {
    renderWithHeader(
      <ActionNodeForm
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

  it('passes projectId to CredentialSelector for HTTP request executor', () => {
    const useQueryMock = vi.mocked(credentialsClient.useQuery)
    useQueryMock.mockClear()

    renderWithHeader(
      <ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} projectId="project-123" />
    )

    const hasProjectIdCall = useQueryMock.mock.calls.some((call) => {
      const params = (call[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params?.query
      return params?.project_id === 'project-123'
    })
    expect(hasProjectIdCall).toBe(true)
  })

  it('validates URL field for API executor', () => {
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

    expect(screen.getByPlaceholderText(/https:\/\/api.example.com/i)).toHaveAttribute('type', 'url')
  })

  it('submits script form data', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

    await user.type(screen.getByPlaceholderText(/Enter your code/i), 'print("hello")')
    fireEvent.submit(screen.getByTestId('action-node-form'))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: '',
          executor: 'script',
          language: 'python',
          code: 'print("hello")',
        })
      )
    })
  })

  it('submits API form data', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

    await user.type(screen.getByPlaceholderText(/https:\/\/api.example.com/i), 'https://api.test.com/data')
    await user.click(screen.getByRole('button', { name: 'HTTP Method' }))
    await user.click(screen.getByRole('option', { name: 'POST' }))
    fireEvent.submit(screen.getByTestId('action-node-form'))

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

  it('allows changing language for script executor', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

    await user.click(screen.getByRole('button', { name: 'Language' }))
    await user.click(screen.getByRole('option', { name: 'Bash' }))
    await user.type(screen.getByPlaceholderText(/Enter your code/i), 'echo "test"')
    fireEvent.submit(screen.getByTestId('action-node-form'))

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          language: 'bash',
        })
      )
    })
  })

  it('includes parameters in submission when provided', async () => {
    const user = userEvent.setup()
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

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
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

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
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

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
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

    expect(screen.getByTestId('code-editor')).toBeInTheDocument()
  })

  it('accepts drop on environment variables field for script executor', () => {
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} />)

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

  it('shows Developer Preview label for script executor', () => {
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'script' }} />)

    expect(screen.getByText('Developer Preview')).toBeInTheDocument()
  })

  it('does not show Developer Preview label for HTTP request executor', () => {
    renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

    expect(screen.queryByText('Developer Preview')).not.toBeInTheDocument()
  })

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
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      created_by: 'user-1',
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
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      created_by: 'user-1',
    }

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
    }

    it('disables URL field and shows locked placeholder when Secret URL credential is selected', async () => {
      const user = userEvent.setup()
      setupSecretUrlMocks()
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))

      const urlInput = screen.getByRole('textbox', { name: 'URL' })
      expect(urlInput).toBeDisabled()
      expect(urlInput).toHaveAttribute('placeholder', 'URL managed by credential')
    })

    it('shows helper text explaining the URL is injected at runtime when Secret URL credential is selected', async () => {
      const user = userEvent.setup()
      setupSecretUrlMocks()
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

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
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))

      expect(screen.getByRole('textbox', { name: 'URL' })).not.toBeRequired()
    })

    it('URL field is enabled and shows normal placeholder with no credential selected', () => {
      vi.mocked(credentialsClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        error: null,
        refetch: vi.fn(),
      } as never)
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      const urlInput = screen.getByRole('textbox', { name: 'URL' })
      expect(urlInput).not.toBeDisabled()
      expect(urlInput).toHaveAttribute('placeholder', 'https://api.example.com/endpoint')
    })

    it('URL field is immediately locked on initial render when initialData includes a Secret URL credential', () => {
      setupSecretUrlMocks()
      renderWithHeader(
        <ActionNodeForm
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
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))
      fireEvent.submit(screen.getByTestId('action-node-form'))

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
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Bearer Token Credential/i }))

      const urlInput = screen.getByRole('textbox', { name: 'URL' })
      expect(urlInput).not.toBeDisabled()
      expect(urlInput).toHaveAttribute('placeholder', 'https://api.example.com/endpoint')
    })

    it('URL field re-enables when switching from a Secret URL to a non-Secret-URL credential', async () => {
      const user = userEvent.setup()
      setupMixedCredentialMocks()
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

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
      vi.mocked(credentialsClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: true,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)
      renderWithHeader(
        <ActionNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ executor: 'http_request', credential_id: 'cred-webhook' }}
        />
      )
      expect(screen.getByRole('textbox', { name: 'URL' })).toBeDisabled()
    })

    it('clears the URL value when a Secret URL credential is selected after typing a URL', async () => {
      const user = userEvent.setup()
      setupSecretUrlMocks()
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.type(screen.getByRole('textbox', { name: 'URL' }), 'https://old.example.com')
      await user.click(screen.getByRole('button', { name: 'Authentication credential' }))
      await user.click(screen.getByRole('option', { name: /Webhook Endpoint/i }))

      expect(screen.getByRole('textbox', { name: 'URL' })).toHaveValue('')
    })

    it('has no accessibility violations in the locked URL state (HttpUrlField in isolation)', async () => {
      // Render HttpUrlField directly — avoids the PatternFly tab aria-controls/id
      // mismatch that occurs in JSDOM when testing the full ActionNodeForm.
      function Wrapper() {
        const { register, getValues, setValue } = useForm<ActionFormValues>({
          defaultValues: { executor: 'http_request', url: '' },
        })
        return (
          <form>
            <HttpUrlField
              register={register}
              getValues={getValues}
              setValue={setValue}
              isUrlManagedByCredential
              isDisabled={false}
            />
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
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'script' }} />)

      await user.click(screen.getByRole('tab', { name: 'Settings' }))

      expect(screen.queryByRole('switch', { name: 'Override retry policy' })).not.toBeInTheDocument()
    })

    it('shows retry policy for HTTP request executor', async () => {
      const user = userEvent.setup()
      renderWithHeader(<ActionNodeForm onSubmit={mockOnSubmit} initialData={{ executor: 'http_request' }} />)

      await user.click(screen.getByRole('tab', { name: 'Settings' }))

      expect(screen.getByRole('switch', { name: 'Override retry policy' })).toBeInTheDocument()
    })

    it('strips retry_policy from submitted data when executor is script', async () => {
      renderWithHeader(
        <ActionNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            executor: 'script',
            code: 'print("hello")',
            settings: { retry_policy: { max_retries: 3, initial_interval: 10 } },
          }}
        />
      )

      fireEvent.submit(screen.getByTestId('action-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            executor: 'script',
            settings: expect.objectContaining({ retry_policy: undefined }) as unknown,
          })
        )
      })
    })
  })
})
