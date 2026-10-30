import { IntegrationTypeEnum, TriggerTypeEnum, type IntegrationsAPI } from '@syntara/contracts'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient, integrationsFetchClient, workflowClient } from '../../../client'
import { submitForm } from '../../../test/submit-form'
import { useAllCredentials } from '../components/useAllCredentials'
import { useBuilderPermissions } from '../useBuilderPermissions'
import { VersionViewContext } from '../VersionViewContext'

import { renderWithHeader } from './test-utils/renderWithHeader'
import type { TriggerFormData } from './triggerFormSchema'
import { TriggerNodeForm } from './TriggerNodeForm'

const mutate = vi.fn()
vi.mock('../../../client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../client')>()),
  integrationsFetchClient: { GET: vi.fn() },
  workflowClient: { useMutation: vi.fn() },
  credentialsClient: { useQuery: vi.fn() },
}))
vi.mock('../../configuration/integrations/useIntegrationPermissions', () => ({
  useIntegrationPermissions: () => ({ canCreate: true }),
}))
vi.mock('../components/useAllCredentials', () => ({ useAllCredentials: vi.fn() }))
vi.mock('../../configuration/credentials/useCredentialPermissions', () => ({
  useCredentialPermissions: () => ({ canCreate: true }),
}))
vi.mock('../useBuilderPermissions', () => ({ useBuilderPermissions: vi.fn() }))
vi.mock('../../../hooks/useMutationErrorHandler', () => ({ useMutationErrorHandler: () => () => vi.fn() }))
vi.mock('../components/CredentialSelector', () => ({
  CredentialSelector: ({
    value,
    onChange,
    isDisabled,
    label,
  }: {
    value?: string
    onChange: (value: string) => void
    isDisabled?: boolean
    label: string
  }) => (
    <input
      aria-label={label}
      value={value ?? ''}
      disabled={isDisabled}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

const integrationId = '11111111-1111-4111-8111-111111111111'
const secondId = '33333333-3333-4333-8333-333333333333'
const credentialId = '22222222-2222-4222-8222-222222222222'
const initialData = {
  triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE,
  integrationId,
  runtimeCredentialId: credentialId,
  topic: 'orders.created',
}
const integration: IntegrationsAPI.components['schemas']['KafkaIntegrationRead'] = {
  id: integrationId,
  name: 'Orders Kafka',
  integration_type: IntegrationTypeEnum.KAFKA,
  enabled: true,
  validation_status: 'available',
  configuration: { integration_type: IntegrationTypeEnum.KAFKA, bootstrap_servers: ['kafka.example.com:9093'] },
}

function setupMutation(overrides = {}) {
  vi.mocked(workflowClient.useMutation).mockReturnValue({
    mutate,
    isPending: false,
    isError: false,
    data: undefined,
    ...overrides,
  })
}

function renderKafka(onSubmit = vi.fn(), workflowId: string | null = 'workflow-1') {
  return renderWithHeader(
    <TriggerNodeForm initialData={initialData} onSubmit={onSubmit} workflowId={workflowId} projectId="project-1" />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
    data: { resources: [integration] },
    response: new Response(),
  })
  vi.mocked(useBuilderPermissions).mockReturnValue({
    canEdit: true,
    tooltips: { edit: 'Edit permission required' },
  } as never)
  vi.mocked(useAllCredentials).mockReturnValue({
    credentials: [
      { id: credentialId, project_id: 'project-1', name: 'Runtime', credential_type_id: 'kafka-type', enabled: true },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })
  vi.mocked(credentialsClient.useQuery).mockReturnValue({
    data: { resources: [{ id: 'kafka-type', name: 'Kafka' }] },
    isPending: false,
    isError: false,
  })
  setupMutation()
})

describe('Kafka Subscribe form', () => {
  it('discloses fixed delivery policies and explains the next publish', async () => {
    const user = userEvent.setup()
    renderKafka()
    expect(screen.getByText(/Configuration changes apply on the next publish/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show message delivery details' }))

    expect(
      screen.getByText(
        'Each subscription uses a platform-managed group. ' +
          'Partitions present at first activation start with new messages at the visible-end boundary saved when each partition initializes. ' +
          'Partitions added later start at their earliest retained message. ' +
          'Initialized partitions resume from valid committed offsets. ' +
          'Missing or invalid established checkpoints require recovery; they do not reset automatically. ' +
          'Auto-commit is off. Commit follows durable scheduling or resolution, without waiting for workflow completion.'
      )
    ).toBeInTheDocument()
  })

  it('loads visible Kafka Integrations scoped to the workflow project and separates identity from authentication', async () => {
    renderKafka()
    expect(await screen.findByRole('button', { name: 'Kafka Integration' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Kafka Integration' })).toHaveValue('Orders Kafka'))
    expect(integrationsFetchClient.GET).toHaveBeenCalledWith(
      '/kafka_integrations',
      expect.objectContaining({
        params: {
          query: { enabled: true, project_id: 'project-1', limit: 100, cursor: undefined },
        },
      })
    )
    expect(screen.getByText(/platform supplies the workflow execution identity automatically/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /service account|execution account/i })).not.toBeInTheDocument()
    expect(screen.getByText('Available')).toBeInTheDocument()
  })

  it('submits Kafka fields without webhook authorization or schedule settings', async () => {
    const onSubmit = vi.fn<(data: TriggerFormData) => void>()
    renderKafka(onSubmit)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kafka Integration' })).toBeEnabled())
    await submitForm()
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining(initialData))
    expect(onSubmit.mock.calls[0]?.[0].authorizedServiceAccountIds).toBeUndefined()
    expect(onSubmit.mock.calls[0]?.[0].interval).toBeUndefined()
  })

  it('tests the unsaved configuration with the generated flat request contract', async () => {
    const user = userEvent.setup()
    renderKafka()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Test runtime access' })).not.toHaveAttribute('aria-disabled', 'true')
    )
    await user.click(screen.getByRole('button', { name: 'Test runtime access' }))
    expect(mutate).toHaveBeenCalledWith(
      {
        params: { path: { workflow_id: 'workflow-1' } },
        body: { integration_id: integrationId, credential_id: credentialId, topic: 'orders.created' },
      },
      expect.any(Object)
    )
  })

  it('does not test invalid topics or workflows that have not been saved', async () => {
    const user = userEvent.setup()
    renderKafka(vi.fn(), null)
    expect(screen.getByText('Save the workflow before testing runtime access.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kafka Integration' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Test runtime access' }))
    expect(mutate).not.toHaveBeenCalled()
  })

  it('clears the runtime credential when another Integration is selected with the keyboard', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
      data: { resources: [integration, { ...integration, id: secondId, name: 'Other Kafka' }] },
      response: new Response(),
    })
    const user = userEvent.setup()
    renderKafka()
    const toggle = await screen.findByRole('button', { name: 'Kafka Integration' })
    await waitFor(() => expect(toggle).toBeEnabled())
    toggle.focus()
    await user.keyboard('{Enter}')
    await user.click(screen.getByRole('option', { name: 'Other Kafka' }))
    expect(screen.getByRole('button', { name: 'Set up connection' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Kafka runtime credential' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Kafka Integration' })).toHaveFocus()
  })

  it('prevents requests without workflow update permission', async () => {
    vi.mocked(useBuilderPermissions).mockReturnValue({
      canEdit: false,
      tooltips: { edit: 'Edit permission required' },
    } as never)
    const user = userEvent.setup()
    renderKafka()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kafka Integration' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Test runtime access' }))
    expect(mutate).not.toHaveBeenCalled()
  })

  it('renders connectivity success while read and group permissions stay explicitly unverified', () => {
    setupMutation({
      data: { success: true, connection: 'verified', topic_metadata: 'verified', checked_at: '2026-01-01T00:00:00Z' },
    })
    renderKafka()
    expect(screen.getByText(/Connection: verified. Topic metadata: verified/)).toBeInTheDocument()
    expect(screen.getByText(/Topic read permission: unverified. Consumer group access: unverified/)).toBeInTheDocument()
  })

  it('shows a safe failed check without rendering broker error text', () => {
    setupMutation({ data: { success: false, connection: 'failed', error_code: 'timeout' } })
    renderKafka()
    expect(screen.getByText('Runtime access check failed')).toBeInTheDocument()
    expect(screen.getByText('Error code: timeout')).toBeInTheDocument()
  })

  it('keeps version views read-only', () => {
    renderWithHeader(
      <VersionViewContext value>
        <TriggerNodeForm initialData={initialData} onSubmit={vi.fn()} workflowId="workflow-1" />
      </VersionViewContext>
    )
    expect(screen.getByRole('textbox', { name: /Topic/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Test runtime access' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('disables preflight while the topic is invalid', async () => {
    const user = userEvent.setup()
    renderKafka()
    await user.clear(screen.getByRole('textbox', { name: 'Topic' }))
    await user.type(screen.getByRole('textbox', { name: 'Topic' }), 'orders.*')
    await submitForm()
    expect(screen.getByRole('textbox', { name: 'Topic' })).toHaveAccessibleDescription(/exact Kafka topic/)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kafka Integration' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Test runtime access' }))
    expect(mutate).not.toHaveBeenCalled()
    expect(
      screen.getByText(
        'Select an available Kafka Integration, a compatible runtime credential, and one exact topic before testing. Payload schema is optional; if supplied, it must be valid.'
      )
    ).toBeInTheDocument()
  })

  it('shows an API failure instead of a misleading empty Integration list', async () => {
    vi.mocked(integrationsFetchClient.GET).mockRejectedValue({
      status: 500,
      title: 'Service unavailable',
      retryable: true,
    })
    renderKafka()
    expect(await screen.findByRole('heading', { name: 'Unable to load Kafka Integrations' })).toBeInTheDocument()
  })

  it('follows Integration pagination so choices beyond the first page are available', async () => {
    vi.mocked(integrationsFetchClient.GET)
      .mockResolvedValueOnce({ data: { resources: [], next: 'next-page' }, response: new Response() })
      .mockResolvedValueOnce({ data: { resources: [integration] }, response: new Response() })
    renderKafka()
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Kafka Integration' })).toHaveValue('Orders Kafka'))
    expect(integrationsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('presents a missing Integration without replacing its saved reference', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({ data: { resources: [] }, response: new Response() })
    renderKafka()
    expect(await screen.findByText(/Select an available Kafka Integration/)).toBeInTheDocument()
  })

  it('uses the Integration status presentation and exposes failure detail', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({
      data: {
        resources: [{ ...integration, validation_status: 'error', validation_error: 'Connection check failed' }],
      },
      response: new Response(),
    })
    const user = userEvent.setup()
    renderKafka()
    await user.hover(await screen.findByText('Error'))
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Connection check failed')
  })

  it('blocks submitting and preflight for an unavailable saved Integration', async () => {
    vi.mocked(integrationsFetchClient.GET).mockResolvedValue({ data: { resources: [] }, response: new Response() })
    const onSubmit = vi.fn()
    renderKafka(onSubmit)
    await screen.findByText('Select an available Kafka Integration')
    expect(screen.getByRole('textbox', { name: 'Kafka Integration' })).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('textbox', { name: 'Kafka Integration' })).toHaveAccessibleDescription(
      /Select an available Kafka Integration/
    )
    await submitForm()
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Test runtime access' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('blocks a saved non-Kafka credential even when its ID is valid', async () => {
    vi.mocked(useAllCredentials).mockReturnValue({
      credentials: [
        { id: credentialId, project_id: 'project-1', name: 'Other', enabled: true, credential_type_id: 'http-type' },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    const onSubmit = vi.fn()
    renderKafka(onSubmit)
    await screen.findByText('Available')
    await submitForm()
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Test runtime access' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('creates an incomplete trigger and allows clearing an existing trigger', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    renderKafka(onSubmit)
    await screen.findByText('Available')
    await user.clear(screen.getByRole('textbox', { name: 'Topic' }))
    await user.click(screen.getByRole('button', { name: 'Change' }))
    await user.clear(screen.getByRole('textbox', { name: 'Kafka runtime credential' }))
    await user.click(screen.getByRole('button', { name: 'Clear selection' }))
    await submitForm()
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ integrationId: '', runtimeCredentialId: '', topic: '' })
    )
    expect(screen.getByRole('button', { name: 'Test runtime access' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByRole('textbox', { name: 'Kafka runtime credential' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Set up connection' })).not.toBeInTheDocument()
  })

  it('searches Kafka Integrations without changing the saved selection', async () => {
    const user = userEvent.setup()
    renderKafka()
    const input = screen.getByRole('textbox', { name: 'Kafka Integration' })
    await waitFor(() => expect(input).toHaveValue('Orders Kafka'))
    await user.click(input)
    await user.type(input, 'not found')
    expect(screen.getByRole('option', { name: 'No matching Kafka Integrations' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Orders Kafka' })).not.toBeInTheDocument()
  })

  it('keeps the Integration menu open and restores options after clearing its filter', async () => {
    const user = userEvent.setup()
    renderKafka()
    const input = screen.getByRole('textbox', { name: 'Kafka Integration' })
    await waitFor(() => expect(input).toHaveValue('Orders Kafka'))
    await user.click(input)
    await user.type(input, 'not found')
    await user.click(screen.getByRole('button', { name: 'Clear filter' }))

    expect(screen.getByRole('listbox', { name: 'Kafka Integrations' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Orders Kafka' })).toBeInTheDocument()
    expect(input).toHaveValue('')
    expect(input).toHaveFocus()
  })

  it('has no accessibility violations, including the expanded Integration selector', async () => {
    const user = userEvent.setup()
    const { container } = renderKafka()
    const toggle = screen.getByRole('button', { name: 'Kafka Integration' })
    await waitFor(() => expect(toggle).toBeEnabled())
    await user.click(toggle)
    expect(
      within(screen.getByRole('listbox', { name: 'Kafka Integrations' })).getByRole('option', { name: 'Orders Kafka' })
    ).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
