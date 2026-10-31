import { Button } from '@patternfly/react-core'
import { ActivityTypeEnum, type Activity } from '@syntara/contracts'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { CredentialSelectorProps } from '../components/CredentialSelector'
import type { IntegrationSelectorProps } from '../components/IntegrationSelector'
import { KafkaPublishNodeDetails } from '../node-details/KafkaPublishNodeDetails'

import { KafkaPublishNodeForm } from './KafkaPublishNodeForm'

const { updateActivity } = vi.hoisted(() => ({ updateActivity: vi.fn() }))

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
  CredentialSelector: ({ value, onChange, isDisabled }: CredentialSelectorProps) => (
    <label>
      Runtime credential
      <input value={value ?? ''} disabled={isDisabled} onChange={(event) => onChange(event.target.value)} />
    </label>
  ),
}))
vi.mock('./shared/NodeSettingsForm', () => ({ NodeSettingsForm: () => null }))

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
  beforeEach(() => vi.clearAllMocks())

  it('offers labeled message controls and has no accessibility violations', async () => {
    const { container } = render(<KafkaPublishNodeForm onSubmit={vi.fn()} />)
    expect(screen.getByRole('textbox', { name: 'Topic' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'JSON payload' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Message key' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Message headers' })).toBeInTheDocument()
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
      expect(updateActivity).toHaveBeenCalledWith('publish_result', expect.objectContaining({ parameters }))
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
})
