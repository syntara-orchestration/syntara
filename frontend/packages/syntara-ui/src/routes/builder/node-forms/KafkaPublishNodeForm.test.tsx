import { Button } from '@patternfly/react-core'
import { ActivityTypeEnum, type Activity } from '@syntara/contracts'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldError } from '../../../components/FormFieldError'
import { getActivityMetadata } from '../../../stores/useWorkflowStore'
import type { ActivityWithMetadata } from '../../../stores/workflowStoreTypes'
import type { CredentialSelectorProps } from '../components/CredentialSelector'
import type { ExpandableCodeEditorProps } from '../components/ExpandableCodeEditor'
import type { IntegrationSelectorProps } from '../components/IntegrationSelector'
import { NodeEditorAutoSubmitContext } from '../hooks/useNodeEditorAutoSubmit'
import { KafkaPublishNodeDetails } from '../node-details/KafkaPublishNodeDetails'
import { VersionViewContext } from '../VersionViewContext'

import { KafkaPublishNodeForm } from './KafkaPublishNodeForm'

const { updateActivity, connection, integrationQuery } = vi.hoisted(() => ({
  updateActivity: vi.fn(),
  connection: { protocol: 'SSL' },
  integrationQuery: vi.fn(),
}))

vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    onBlur,
    ariaLabel,
    language,
    isReadOnly,
    isRequired,
  }: ExpandableCodeEditorProps) => (
    <textarea
      aria-label={ariaLabel}
      aria-required={isRequired}
      data-language={language}
      readOnly={isReadOnly}
      value={code}
      onChange={(event) => onCodeChange(event.target.value)}
      onBlur={() => onBlur?.(code)}
    />
  ),
}))
vi.mock('../../../client', () => ({
  integrationsClient: { useQuery: integrationQuery },
}))
vi.mock('../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: () => ({ defaults: null, isLoading: false }),
}))
vi.mock('../../workflows/canvas/nodes/hooks/useCredentialName', () => ({
  useCredentialName: (id?: string) => ({ name: id ? 'Publish runtime credential' : undefined, isPending: false }),
}))

vi.mock('../../../stores/useWorkflowStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../stores/useWorkflowStore')>()),
  useWorkflowStoreActions: () => ({ updateActivity }),
}))
vi.mock('../components/IntegrationSelector', () => ({
  IntegrationSelector: ({ value, onChange, isDisabled }: IntegrationSelectorProps) => (
    <label>
      Integration
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
  credential_id: '22222222-2222-4222-8222-222222222222',
  topic: 'automation.outcomes',
  payload: null,
  key: { encoding: 'base64', value: 'AAEC' },
  headers: [
    { name: 'x', value: null },
    { name: 'x', value: { encoding: 'utf-8', value: '' } },
  ],
}

// Sortable keyboard navigation needs row geometry, which happy-dom does not lay out.
function mockHeaderLayout() {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const header = this.getAttribute('aria-label')?.match(/^Header (\d+)$/)
    return header ? new DOMRect(0, (Number(header[1]) - 1) * 240, 600, 220) : new DOMRect()
  })
}

describe('Kafka Publish builder', () => {
  afterEach(() => vi.restoreAllMocks())

  beforeEach(() => {
    vi.clearAllMocks()
    updateActivity.mockReset()
    connection.protocol = 'SSL'
    integrationQuery.mockImplementation(() => ({ data: { configuration: { security_protocol: connection.protocol } } }))
  })

  it('offers labeled message controls and has no accessibility violations', async () => {
    const { container } = render(<KafkaPublishNodeForm onSubmit={vi.fn()} />)
    expect(screen.getByRole('textbox', { name: 'Target topic' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Target topic' })).toHaveAccessibleDescription(
      'Enter an existing Kafka topic name. Expressions are not supported.'
    )
    expect(screen.getByRole('textbox', { name: 'JSON payload' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Message key encoding' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Header source' })).toBeInTheDocument()
    expect(screen.getByText('Configure headers sent with each Kafka message.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Add header' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it.each([
    ['null', 'json'],
    ['[1,true,null]', 'json'],
    ['"a string"', 'json'],
    ['42', 'json'],
    ['{"order_id":"${trigger.payload.order_id}"}', 'json'],
    ['${trigger.payload}', 'plaintext'],
  ])('uses the appropriate editor mode for %s', (payload, language) => {
    render(<KafkaPublishNodeForm onSubmit={vi.fn()} initialData={{ payload }} />)
    const editor = screen.getByRole('textbox', { name: 'JSON payload' })
    expect(editor).toHaveValue(payload)
    expect(editor).toHaveAttribute('data-language', language)
    expect(editor).toHaveAttribute('aria-required', 'true')
  })

  it('keeps entry rules visible and offers template and array guidance through keyboard-accessible field help', async () => {
    const user = userEvent.setup()
    const { container } = render(<KafkaPublishNodeForm onSubmit={vi.fn()} />)
    expect(
      screen.getByText(
        'Enter a valid JSON value (quote strings) or use a trigger input such as ${trigger.payload}. Declare referenced inputs in the trigger first. A JSON null is sent as JSON null, not as a Kafka tombstone.'
      )
    ).toBeVisible()
    expect(screen.queryByText(/Arrays are sent as one Kafka record/)).not.toBeInTheDocument()

    const help = screen.getByRole('button', { name: 'More info for JSON payload' })
    help.focus()
    await user.keyboard('{Enter}')
    expect(await screen.findByRole('dialog', { name: 'JSON payload' })).toBeVisible()
    expect(screen.getByText(/Templates can replace the full payload or appear inside JSON strings/)).toHaveTextContent(
      'Templates can replace the full payload or appear inside JSON strings. Example: {"order_id":"${trigger.payload.order_id}"}. Arrays are sent as one Kafka record.'
    )
    expect(screen.getByText(/Arrays are sent as one Kafka record/)).toHaveTextContent(
      '{"order_id":"${trigger.payload.order_id}"}'
    )
    expect(await axe(container)).toHaveNoViolations()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'JSON payload' })).not.toBeInTheDocument())
    expect(help).toHaveFocus()
  })

  it('shows compact credential setup after an integration is selected', async () => {
    connection.protocol = 'SASL_SSL'
    const user = userEvent.setup()
    const { container } = render(<KafkaPublishNodeForm onSubmit={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'Set up connection' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Runtime credential' })).not.toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Integration' }), parameters.integration_id)
    expect(screen.queryByText('Wait for the selected Kafka connection settings to load')).not.toBeInTheDocument()
    expect(screen.getByText('Kafka credential not configured')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Runtime credential' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Set up connection' }))
    expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toBeEnabled()
    expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toHaveAttribute('aria-required', 'true')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('textbox', { name: 'Runtime credential' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Set up connection' })).toHaveFocus()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('collapses credential setup after selection and preserves the selection when Change is cancelled', async () => {
    connection.protocol = 'SASL_SSL'
    const user = userEvent.setup()
    const { container } = render(
      <KafkaPublishNodeForm onSubmit={vi.fn()} initialData={{ integration_id: parameters.integration_id }} />
    )

    await user.click(screen.getByRole('button', { name: 'Set up connection' }))
    await user.click(screen.getByRole('textbox', { name: 'Runtime credential' }))
    await user.paste('22222222-2222-4222-8222-222222222222')
    expect(screen.getByText('Publish runtime credential')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Runtime credential' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Change' }))
    expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toHaveValue(
      '22222222-2222-4222-8222-222222222222'
    )
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('button', { name: 'Change' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Change' }))
    expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toHaveValue(
      '22222222-2222-4222-8222-222222222222'
    )
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

  it.each([true, false, undefined])(
    'preserves disabled=%s through editing and reopening while clearing retry overrides',
    async (disabled) => {
      const user = userEvent.setup()
      const stored: { activity?: Activity } = {}
      updateActivity.mockImplementationOnce((_id: string, activity: Activity) => {
        stored.activity = activity
      })
      const activity: Activity = {
        id: 'disabled-publish',
        name: 'Publish result',
        type: ActivityTypeEnum.KAFKA_PUBLISH,
        parameters,
        settings: { ...(disabled !== undefined && { disabled }), timeout: 30, retry_policy: { max_retries: 2 } },
      }
      const view = render(
        <>
          <KafkaPublishNodeDetails taskData={activity} onClose={vi.fn()} />
          <Button type="submit" form="kafka-publish-node-form">
            Save
          </Button>
        </>
      )
      await user.clear(screen.getByRole('textbox', { name: 'Target topic' }))
      await user.type(screen.getByRole('textbox', { name: 'Target topic' }), 'outcomes.updated')
      await user.clear(screen.getByRole('textbox', { name: 'JSON payload' }))
      await user.click(screen.getByRole('textbox', { name: 'JSON payload' }))
      await user.paste('{"result":"updated"}')
      await user.click(screen.getByRole('tab', { name: 'Settings' }))
      await user.click(screen.getByRole('switch', { name: 'Override retry policy' }))
      await user.click(screen.getByRole('button', { name: 'Save' }))
      await waitFor(() => expect(updateActivity).toHaveBeenCalledOnce())
      const saved = stored.activity
      if (!saved) throw new Error('The edited Kafka Publish step was not saved')
      expect(saved.settings?.disabled).toBe(disabled)
      expect(saved.settings?.timeout).toBe(30)
      expect(saved.settings?.retry_policy).toBeUndefined()
      expect(saved.parameters).toMatchObject({ topic: 'outcomes.updated', payload: { result: 'updated' } })

      view.unmount()
      render(<KafkaPublishNodeDetails taskData={saved} onClose={vi.fn()} />)
      expect(screen.getByRole('textbox', { name: 'Target topic' })).toHaveValue('outcomes.updated')
      expect(screen.getByRole('textbox', { name: 'JSON payload' })).toHaveValue(
        JSON.stringify({ result: 'updated' }, null, 2)
      )
      await user.click(screen.getByRole('tab', { name: 'Settings' }))
      expect(screen.getByRole('switch', { name: 'Override retry policy' })).not.toBeChecked()
      expect(saved.settings?.disabled).toBe(disabled)
    }
  )

  it('saves a draft with a templated topic while retaining validation feedback', async () => {
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
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
    onSubmit.mockClear()
    expect(await screen.findByText('Enter one literal Kafka topic name')).toBeInTheDocument()
  })

  it('supports keyboard activation of settings and preserves entered data', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <KafkaPublishNodeForm onSubmit={vi.fn()} initialData={{ topic: 'outcomes', payload: 'null' }} />
    )
    const parametersTab = screen.getByRole('tab', { name: 'Parameters' })
    expect(screen.getByRole('heading', { name: /Message delivery behavior/ })).toBeVisible()
    expect(screen.getAllByText(/Kafka acknowledgment confirms broker receipt/)).toHaveLength(1)
    screen.getByRole('tab', { name: 'Settings' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('tab', { name: 'Settings' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByText('Timeout (seconds)')).toHaveLength(1)
    expect(screen.getByRole('spinbutton', { name: 'Timeout (seconds)' })).toBeEnabled()
    expect(screen.queryByText(/Kafka acknowledgment confirms broker receipt/)).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
    await user.click(parametersTab)
    expect(screen.getByRole('heading', { name: /Message delivery behavior/ })).toBeVisible()
    expect(screen.getAllByText(/Kafka acknowledgment confirms broker receipt/)).toHaveLength(1)
    expect(screen.getByRole('textbox', { name: 'JSON payload' })).toHaveValue('null')
    expect(screen.getByRole('textbox', { name: 'Target topic' })).toHaveValue('outcomes')
  })

  it.each(['SASL_SSL', 'SSL', 'PLAINTEXT'])(
    'reports a missing runtime Kafka credential for %s while allowing drafts',
    async (protocol) => {
      connection.protocol = protocol
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
      expect(screen.getByText('Kafka credential not configured')).toBeInTheDocument()
      expect(screen.queryByRole('textbox', { name: 'Runtime credential' })).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Save' }))
      expect(await screen.findByText('Select a runtime Kafka credential')).toBeInTheDocument()
      await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
      onSubmit.mockClear()
      expect(await axe(container)).toHaveNoViolations()
      await user.click(screen.getByRole('button', { name: 'Set up connection' }))
      expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toHaveAttribute('aria-required', 'true')
      expect(screen.getByRole('status', { name: 'Credential compatibility' })).toHaveTextContent(
        'Kafka:workflow-project'
      )
      await user.click(screen.getByRole('textbox', { name: 'Runtime credential' }))
      await user.paste('22222222-2222-4222-8222-222222222222')
      await user.click(screen.getByRole('button', { name: 'Save' }))
      await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
    }
  )

  it('clears a previous credential and requires a new selection when switching to SSL', async () => {
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
    await user.clear(screen.getByRole('textbox', { name: 'Integration' }))
    await user.type(screen.getByRole('textbox', { name: 'Integration' }), '33333333-3333-4333-8333-333333333333')
    expect(screen.queryByText('Publish runtime credential')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Runtime credential' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
    onSubmit.mockClear()
    expect(await screen.findByText('Select a runtime Kafka credential')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Set up connection' }))
    expect(screen.getByRole('textbox', { name: 'Runtime credential' })).toHaveValue('')
    await user.click(screen.getByRole('textbox', { name: 'Runtime credential' }))
    await user.paste('44444444-4444-4444-8444-444444444444')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ credential_id: '44444444-4444-4444-8444-444444444444' }),
        expect.anything()
      )
    )
  })

  it('adds, reorders and removes headers with the keyboard while preserving null and empty bytes', async () => {
    mockHeaderLayout()
    const user = userEvent.setup()
    const { container } = render(
      <KafkaPublishNodeDetails
        taskData={{ id: 'publish', type: ActivityTypeEnum.KAFKA_PUBLISH, parameters }}
        onClose={vi.fn()}
      />
    )
    expect(screen.getByText('Drag to reorder headers.')).toBeVisible()
    expect(screen.queryByRole('button', { name: /Move header/ })).not.toBeInTheDocument()
    const grip = screen.getByRole('button', { name: 'Reorder header 2' })
    grip.focus()
    await user.keyboard('[Space]')
    await waitFor(() => expect(grip).toHaveAttribute('aria-pressed', 'true'))
    await user.keyboard('{ArrowUp}')
    expect(await screen.findByText('Header 2 is over position 1 of 2.')).toBeInTheDocument()
    await user.keyboard('[Space]')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reorder header 1' })).toHaveFocus())
    expect(screen.getByRole('button', { name: 'Reorder header 1' })).toBe(grip)
    expect(screen.getByRole('button', { name: 'Header 1 encoding' })).toHaveTextContent('UTF-8 text')
    expect(screen.getByRole('textbox', { name: 'Header 1 value' })).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Header 2 encoding' })).toHaveTextContent('Null')
    await user.click(screen.getByRole('button', { name: 'Add header' }))
    expect(screen.getByRole('textbox', { name: 'Header 3 name' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Remove header 3' }))
    expect(screen.queryByRole('textbox', { name: 'Header 3 name' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Header 2 name' })).toHaveFocus()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('cancels a keyboard header move without changing order and retains grip focus', async () => {
    mockHeaderLayout()
    const user = userEvent.setup()
    render(
      <KafkaPublishNodeDetails
        taskData={{ id: 'publish', type: ActivityTypeEnum.KAFKA_PUBLISH, parameters }}
        onClose={vi.fn()}
      />
    )
    const grip = screen.getByRole('button', { name: 'Reorder header 2' })
    grip.focus()
    await user.keyboard('[Space]')
    await waitFor(() => expect(grip).toHaveAttribute('aria-pressed', 'true'))
    await user.keyboard('{ArrowUp}')
    expect(await screen.findByText('Header 2 is over position 1 of 2.')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(grip).toHaveFocus())
    expect(screen.getByRole('button', { name: 'Header 1 encoding' })).toHaveTextContent('Null')
    expect(screen.getByRole('textbox', { name: 'Header 2 value' })).toHaveValue('')
    expect(await screen.findByText('Header reorder cancelled.')).toBeInTheDocument()
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
    expect(screen.getByText('Configure headers sent with each Kafka message.')).toBeVisible()
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
    for (const textbox of screen.getAllByRole('textbox')) {
      if (textbox.getAttribute('aria-label') === 'JSON payload') expect(textbox).toHaveAttribute('readonly')
      else expect(textbox).toBeDisabled()
    }
    expect(screen.queryByRole('button', { name: 'Set up connection' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Message key encoding' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Add header' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Remove header/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reorder header 1' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reorder header 2' })).toBeDisabled()
    expect(screen.queryByText('Drag to reorder headers.')).not.toBeInTheDocument()
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

  it('saves a draft while connection settings load without showing an integration warning', async () => {
    integrationQuery.mockReturnValue({ data: undefined, isError: false })
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const view = render(
      <>
        <KafkaPublishNodeForm
          onSubmit={onSubmit}
          initialData={{
            integration_id: parameters.integration_id,
            credential_id: parameters.credential_id,
            topic: 'outcomes',
          }}
        />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    const change = screen.getByRole('button', { name: 'Change' })
    expect(change).toBeDisabled()
    expect(screen.queryByRole('textbox', { name: 'Runtime credential' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
    onSubmit.mockClear()
    expect(screen.queryByText('Wait for the selected Kafka connection settings to load')).not.toBeInTheDocument()
    expect(screen.queryByText('Kafka connection settings are not available')).not.toBeInTheDocument()
    expect(screen.queryByText('Select a runtime Kafka credential')).not.toBeInTheDocument()
    integrationQuery.mockReturnValue({ data: { configuration: { security_protocol: 'SSL' } }, isError: false })
    view.rerender(
      <>
        <KafkaPublishNodeForm
          onSubmit={onSubmit}
          projectId="loaded-project"
          initialData={{
            integration_id: parameters.integration_id,
            credential_id: parameters.credential_id,
            topic: 'outcomes',
          }}
        />
        <Button type="submit" form="kafka-publish-node-form">
          Save
        </Button>
      </>
    )
    await waitFor(() => expect(change).toBeEnabled())
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

  it('reopens unfinished JSON and auto-submits a draft from the open editor', async () => {
    const onClose = vi.fn()
    const autoSubmitRef: { current: (() => Promise<boolean>) | null } = { current: null }
    render(
      <NodeEditorAutoSubmitContext value={autoSubmitRef}>
        <KafkaPublishNodeDetails
          taskData={
            {
              id: 'unfinished',
              type: ActivityTypeEnum.KAFKA_PUBLISH,
              parameters: { integration_id: '', credential_id: '', topic: '', payload: undefined },
              metadata: { __kafkaPublishPayloadDraft: '{"result":' },
            } satisfies ActivityWithMetadata
          }
          onClose={onClose}
        />
      </NodeEditorAutoSubmitContext>
    )
    expect(screen.getByRole('textbox', { name: 'JSON payload' })).toHaveValue('{"result":')
    let submitted: boolean | undefined
    await act(async () => {
      submitted = await autoSubmitRef.current?.()
    })
    expect(submitted).toBe(true)
    const updated: unknown = updateActivity.mock.calls.at(-1)?.[1]
    expect(updateActivity.mock.calls.at(-1)?.[0]).toBe('unfinished')
    expect(updated).toMatchObject({
      parameters: { payload: undefined, credential_id: '' },
      metadata: { __kafkaPublishPayloadDraft: '{"result":' },
    })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('retains only string payload draft metadata when reopening untrusted workflow data', () => {
    expect(getActivityMetadata({ metadata: { __kafkaPublishPayloadDraft: '{"result":', injected: true } })).toEqual({
      __kafkaPublishPayloadDraft: '{"result":',
    })
    expect(getActivityMetadata({ metadata: { __kafkaPublishPayloadDraft: { injected: true } } })).toEqual({})
  })
})
