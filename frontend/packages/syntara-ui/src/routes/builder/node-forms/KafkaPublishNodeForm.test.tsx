import { Button } from '@patternfly/react-core'
import { ActivityTypeEnum, type Activity } from '@syntara/contracts'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldError } from '../../../components/FormFieldError'
import type { CredentialSelectorProps } from '../components/CredentialSelector'
import type { IntegrationSelectorProps } from '../components/IntegrationSelector'
import { KafkaPublishNodeDetails } from '../node-details/KafkaPublishNodeDetails'
import { VersionViewContext } from '../VersionViewContext'

import { KafkaPublishNodeForm } from './KafkaPublishNodeForm'

const { updateActivity, connection, integrationQuery } = vi.hoisted(() => ({
  updateActivity: vi.fn(),
  connection: { protocol: 'SSL' },
  integrationQuery: vi.fn(),
}))

vi.mock('../../../client', () => ({
  integrationsClient: { useQuery: integrationQuery },
}))
vi.mock('../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: () => ({ defaults: null, isLoading: false }),
}))

vi.mock('../../../stores/useWorkflowStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../stores/useWorkflowStore')>()),
  useWorkflowStoreActions: () => ({ updateActivity }),
}))
vi.mock('../components/IntegrationSelector', () => ({
  IntegrationSelector: ({ value, onChange, isDisabled }: IntegrationSelectorProps) => (
    <label>
      Kafka integration
      <input value={value ?? ''} disabled={isDisabled} onChange={(event) => onChange(event.target.value)} />
    </label>
  ),
}))
vi.mock('../components/CredentialSelector', () => ({
  CredentialSelector: ({
    value,
    onChange,
    isDisabled,
    isRequired,
    errorMessage,
    compatibleTypeNames,
    projectId,
  }: CredentialSelectorProps) => (
    <>
      <label>
        Runtime credential
        <input
          aria-required={isRequired}
          value={value ?? ''}
          disabled={isDisabled}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
      <FormFieldError message={errorMessage} />
      <output aria-label="Credential compatibility">
        {compatibleTypeNames?.join(',')}:{projectId}
      </output>
    </>
  ),
}))

const parameters = {
  integration_id: '11111111-1111-4111-8111-111111111111',
  credential_id: null,
  topic: 'automation.outcomes',
  payload: null,
  key: { encoding: 'base64', value: 'AAEC' },
  headers: [
    { name: 'x', value: null },
    { name: 'x', value: { encoding: 'utf-8', value: '' } },
  ],
}

describe('Kafka Publish builder', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    connection.protocol = 'SSL'
    integrationQuery.mockImplementation(() => ({ data: { configuration: { security_protocol: connection.protocol } } }))
  })

  it('offers labeled message controls and has no accessibility violations', async () => {
    const { container } = render(<KafkaPublishNodeForm onSubmit={vi.fn()} />)
    expect(screen.getByRole('textbox', { name: 'Topic' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'JSON payload' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Message key encoding' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Header source' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add header' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('edits and saves without changing null, binary bytes or duplicate headers', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const activity: Activity = {
      id: 'publish_result',
      name: 'Publish result',
      type: ActivityTypeEnum.KAFKA_PUBLISH,
      parameters,
      outputs: { published_offset: 'offset' },
      settings: { timeout: 30, retry_policy: { max_retries: 0 } },
    }
    const { container } = render(
      <>
        <KafkaPublishNodeDetails taskData={activity} onClose={onClose} />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    expect(screen.getByRole('textbox', { name: 'JSON payload' })).toHaveValue('null')
    expect(await axe(container)).toHaveNoViolations()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(updateActivity).toHaveBeenCalledWith(
        'publish_result',
        expect.objectContaining({ parameters, outputs: activity.outputs, settings: activity.settings })
      )
    )
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('prevents saving a templated topic', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <>
        <KafkaPublishNodeForm
          onSubmit={onSubmit}
          initialData={{ integration_id: parameters.integration_id, topic: '${trigger.topic}' }}
        />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(await screen.findByText('Enter one literal Kafka topic name')).toBeInTheDocument()
  })

  it('supports keyboard activation of settings and preserves entered data', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <KafkaPublishNodeForm onSubmit={vi.fn()} initialData={{ topic: 'outcomes', payload: 'null' }} />
    )
    const parametersTab = screen.getByRole('tab', { name: 'Parameters' })
    screen.getByRole('tab', { name: 'Settings' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('tab', { name: 'Settings' })).toHaveAttribute('aria-selected', 'true')
    expect(await axe(container)).toHaveNoViolations()
    await user.click(parametersTab)
    expect(screen.getByRole('textbox', { name: 'JSON payload' })).toHaveValue('null')
    expect(screen.getByRole('textbox', { name: 'Topic' })).toHaveValue('outcomes')
  })

  it('requires a runtime Kafka credential for SASL_SSL and scopes compatible choices', async () => {
    connection.protocol = 'SASL_SSL'
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = render(
      <>
        <KafkaPublishNodeForm
          onSubmit={onSubmit}
          projectId="workflow-project"
          initialData={{ integration_id: parameters.integration_id, topic: 'outcomes' }}
        />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toHaveAttribute('aria-required', 'true')
    expect(screen.getByRole('status', { name: 'Credential compatibility' })).toHaveTextContent('Kafka:workflow-project')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Select a runtime Kafka credential for SASL_SSL')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
    expect(await axe(container)).toHaveNoViolations()
    await user.type(screen.getByRole('textbox', { name: 'Runtime credential' }), '22222222-2222-4222-8222-222222222222')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
  })

  it('clears a previous credential and permits omission when switching to SSL', async () => {
    connection.protocol = 'SASL_SSL'
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <>
        <KafkaPublishNodeForm
          onSubmit={onSubmit}
          initialData={{
            integration_id: parameters.integration_id,
            credential_id: '22222222-2222-4222-8222-222222222222',
            topic: 'outcomes',
          }}
        />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    connection.protocol = 'SSL'
    await user.clear(screen.getByRole('textbox', { name: 'Kafka integration' }))
    await user.type(screen.getByRole('textbox', { name: 'Kafka integration' }), '33333333-3333-4333-8333-333333333333')
    expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toHaveValue('')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ credential_required: false, credential_id: '' }),
        expect.anything()
      )
    )
  })

  it('adds, reorders and removes headers with the keyboard while preserving null and empty bytes', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <KafkaPublishNodeDetails
        taskData={{ id: 'publish', type: ActivityTypeEnum.KAFKA_PUBLISH, parameters }}
        onClose={vi.fn()}
      />
    )
    screen.getByRole('button', { name: 'Move header 2 up' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('button', { name: 'Header 1 encoding' })).toHaveTextContent('UTF-8 text')
    expect(screen.getByRole('textbox', { name: 'Header 1 name' })).toHaveFocus()
    expect(screen.getByRole('textbox', { name: 'Header 1 value' })).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Header 2 encoding' })).toHaveTextContent('Null')
    await user.click(screen.getByRole('button', { name: 'Add header' }))
    expect(screen.getByRole('textbox', { name: 'Header 3 name' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Remove header 3' }))
    expect(screen.queryByRole('textbox', { name: 'Header 3 name' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Header 2 name' })).toHaveFocus()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows precise Base64 feedback and preserves the value when switching to text', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <KafkaPublishNodeForm onSubmit={vi.fn()} initialData={{ key: { encoding: 'base64', value: 'invalid bytes' } }} />
    )
    const value = screen.getByRole('textbox', { name: 'Message key value' })
    await user.click(value)
    await user.paste('!')
    expect(await screen.findByText('Enter valid standard Base64 or a template')).toBeInTheDocument()
    expect(value).toHaveAttribute('aria-invalid', 'true')
    expect(await axe(container)).toHaveNoViolations()
    await user.click(screen.getByRole('button', { name: 'Message key encoding' }))
    await user.click(screen.getByRole('option', { name: 'UTF-8 text' }))
    expect(screen.getByRole('textbox', { name: 'Message key value' })).toHaveValue('invalid bytes!')
  })

  it('reopens full-value payload and header templates without converting them to JSON objects', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <>
        <KafkaPublishNodeDetails
          taskData={{
            id: 'publish',
            type: ActivityTypeEnum.KAFKA_PUBLISH,
            parameters: { ...parameters, payload: '${trigger.payload}', headers: '${trigger.payload.headers}' },
          }}
          onClose={vi.fn()}
        />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    expect(screen.getByRole('textbox', { name: 'Headers template' })).toHaveValue('${trigger.payload.headers}')
    expect(await axe(container)).toHaveNoViolations()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(updateActivity).toHaveBeenCalledWith(
        'publish',
        expect.objectContaining({
          parameters: { ...parameters, payload: '${trigger.payload}', headers: '${trigger.payload.headers}' },
        })
      )
    )
  })

  it('disables message, connection, and settings controls in a published version', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <VersionViewContext value={true}>
        <KafkaPublishNodeDetails
          taskData={{
            id: 'publish',
            type: ActivityTypeEnum.KAFKA_PUBLISH,
            parameters,
            settings: { timeout: 30, retry_policy: { max_retries: 0 } },
          }}
          onClose={vi.fn()}
        />
      </VersionViewContext>
    )
    for (const textbox of screen.getAllByRole('textbox')) expect(textbox).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Message key encoding' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Add header' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Remove header/ })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
    await user.click(screen.getByRole('tab', { name: 'Settings' }))
    expect(screen.getByRole('spinbutton', { name: 'Timeout (seconds)' })).toBeDisabled()
    expect(screen.getByRole('spinbutton', { name: 'Max retries' })).toHaveValue(0)
    expect(screen.getByRole('spinbutton', { name: 'Max retries' })).toBeDisabled()
    expect(await axe(container)).toHaveNoViolations()
    expect(updateActivity).not.toHaveBeenCalled()
  })

  it('reports malformed saved structures without displaying their contents', () => {
    render(
      <KafkaPublishNodeDetails
        taskData={{
          id: 'publish',
          type: ActivityTypeEnum.KAFKA_PUBLISH,
          parameters: { ...parameters, key: { encoding: 'unknown', value: 'sensitive diagnostic' } },
        }}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByRole('heading', { name: 'Invalid Kafka Publish configuration' })).toBeInTheDocument()
    expect(screen.queryByText('sensitive diagnostic')).not.toBeInTheDocument()
  })

  it('keeps credential selection disabled while connection settings are loading and recovers after loading', async () => {
    integrationQuery.mockReturnValue({ data: undefined, isError: false })
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const view = render(
      <>
        <KafkaPublishNodeForm
          onSubmit={onSubmit}
          initialData={{ integration_id: parameters.integration_id, topic: 'outcomes' }}
        />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Wait for the selected Kafka connection settings to load')).toBeInTheDocument()
    expect(screen.queryByText('Select a runtime Kafka credential for SASL_SSL')).not.toBeInTheDocument()
    integrationQuery.mockReturnValue({ data: { configuration: { security_protocol: 'SSL' } }, isError: false })
    view.rerender(
      <>
        <KafkaPublishNodeForm
          onSubmit={onSubmit}
          projectId="loaded-project"
          initialData={{ integration_id: parameters.integration_id, topic: 'outcomes' }}
        />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    await waitFor(() =>
      expect(screen.queryByText('Wait for the selected Kafka connection settings to load')).not.toBeInTheDocument()
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
  })

  it('offers a retry for connection lookup failures with accessible feedback', async () => {
    const refetch = vi.fn().mockResolvedValue(undefined)
    integrationQuery.mockReturnValue({
      data: undefined,
      isError: true,
      error: { status: 500, title: 'Unable to load connection' },
      refetch,
    })
    const user = userEvent.setup()
    const { container } = render(
      <KafkaPublishNodeForm onSubmit={vi.fn()} initialData={{ integration_id: parameters.integration_id }} />
    )
    expect(screen.getByRole('heading', { name: 'Unable to load Kafka connection settings' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalledOnce()
    expect(await axe(container)).toHaveNoViolations()
  })
})
