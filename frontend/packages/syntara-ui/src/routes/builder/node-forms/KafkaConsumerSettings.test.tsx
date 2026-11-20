import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { workflowFetchClient } from '../../../client'
import { SynTextField } from '../../../components/forms/SynTextField'

import { KafkaConsumerSettings } from './KafkaConsumerSettings'
import { buildKafkaSubscribeTrigger } from './kafkaSubscribeMapping'
import { zodResolver } from './shared/formSchemaUtils'
import { triggerFormSchema, type TriggerFormData } from './triggerFormSchema'

vi.mock('../../../client', () => ({ workflowFetchClient: { GET: vi.fn() } }))

const GROUP = 'Consumer group ID'
const initialData = {
  triggerType: 'event_subscribe_trigger',
  integrationId: '11111111-1111-4111-8111-111111111111',
  topic: 'orders',
}

function renderSettings({
  isReadOnly = false,
  existing = false,
  data = {},
  onSubmit = vi.fn(),
}: {
  isReadOnly?: boolean
  existing?: boolean
  data?: Partial<TriggerFormData>
  onSubmit?: (data: TriggerFormData) => void
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function Wrapper() {
    const form = useForm({
      defaultValues: { ...initialData, ...data },
      resolver: zodResolver(triggerFormSchema, undefined, { mode: 'sync' }),
      mode: 'onBlur',
    })
    return (
      <QueryClientProvider client={client}>
        <FormProvider {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <SynTextField name="topic" label="Topic" />
            <KafkaConsumerSettings
              isReadOnly={isReadOnly}
              workflowId={existing ? 'workflow-1' : undefined}
              triggerId={existing ? 'subscribe' : undefined}
            />
            <button type="submit">Save settings</button>
          </form>
        </FormProvider>
      </QueryClientProvider>
    )
  }
  return { ...render(<Wrapper />), client }
}

describe('Kafka consumer settings', () => {
  it('displays defaults without inserting consumption overrides on save', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn<(data: TriggerFormData) => void>()
    const { container } = renderSettings({ onSubmit })
    expect(screen.getByRole('button', { name: 'Start position' })).toHaveTextContent('Latest')
    expect(screen.getByRole('button', { name: 'New partition position' })).toHaveTextContent('Earliest')
    expect(screen.getByRole('button', { name: 'Offset gap policy' })).toHaveTextContent('Earliest')
    expect(screen.getByRole('textbox', { name: GROUP })).toHaveValue('')
    await user.click(screen.getByRole('button', { name: 'Start position' }))
    expect(screen.getByRole('option', { name: 'Latest' })).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ topic: 'orders' }), expect.anything())
    const saved = onSubmit.mock.calls[0]?.[0]
    if (!saved) throw new Error('Settings were not submitted')
    const trigger = buildKafkaSubscribeTrigger('subscribe', 'Orders', saved)
    expect(trigger.parameters).not.toHaveProperty('start')
    expect(trigger.parameters).not.toHaveProperty('group_id')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('changes policies with the keyboard, preserves partial fields and excludes Inherit', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = renderSettings({ onSubmit, data: { kafkaStart: { position: 'earliest' } } })
    const toggle = screen.getByRole('button', { name: 'Offset gap policy' })
    toggle.focus()
    await user.keyboard('{Enter}')
    const list = screen.getByRole('listbox', { name: 'Offset gap policy options' })
    expect(within(list).queryByRole('option', { name: 'Inherit' })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
    await user.keyboard('{ArrowDown}{Enter}')
    expect(toggle).toHaveFocus()
    await user.type(screen.getByRole('textbox', { name: GROUP }), 'orders-consumer')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        kafkaStart: { position: 'earliest', offset_gap_policy: 'fail' },
        kafkaGroupId: 'orders-consumer',
      }),
      expect.anything()
    )
  })

  it('associates group validation errors with the input and allows correction', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = renderSettings({ onSubmit })
    const group = screen.getByRole('textbox', { name: GROUP })
    await user.type(group, 'invalid group')
    await user.tab()
    expect(
      await screen.findByText('Use 1–512 ASCII letters, numbers, dots, underscores, or hyphens')
    ).toBeInTheDocument()
    expect(group).toHaveAccessibleDescription(/Use 1–512 ASCII/)
    expect(group).toHaveAttribute('aria-invalid', 'true')
    expect(await axe(container)).toHaveNoViolations()
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(onSubmit).not.toHaveBeenCalled()
    await user.clear(group)
    await user.type(group, 'valid.group_1-2')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(onSubmit).toHaveBeenCalled()
    expect(group).toHaveAttribute('aria-invalid', 'false')
  })

  it('shows a read-only group and disables policy controls in version views', async () => {
    vi.mocked(workflowFetchClient.GET).mockClear()
    const { container } = renderSettings({
      isReadOnly: true,
      existing: true,
      data: { kafkaStart: { position: 'earliest', offset_gap_policy: 'fail' }, kafkaGroupId: 'saved-group' },
    })
    for (const name of ['Start position', 'New partition position', 'Offset gap policy']) {
      expect(screen.getByRole('button', { name })).toBeDisabled()
    }
    expect(screen.getByRole('group', { name: GROUP })).toHaveTextContent('saved-group')
    expect(screen.queryByRole('textbox', { name: GROUP })).not.toBeInTheDocument()
    expect(workflowFetchClient.GET).not.toHaveBeenCalled()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('locks a previously published source and unlocks a replacement topic', async () => {
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: {
        kafka_subscription_sources: [
          {
            trigger_node_id: 'subscribe',
            source_id: 'source-1',
            generation: 1,
            configuration_revision: 1,
            group_id_is_generated: false,
            integration_id: initialData.integrationId,
            topic: 'orders',
            group_id: 'published-group',
          },
        ],
      },
      response: new Response(),
    })
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = renderSettings({ existing: true, data: { kafkaGroupId: 'published-group' }, onSubmit })
    const group = await screen.findByRole('group', { name: GROUP })
    expect(group).toHaveTextContent('published-group')
    expect(screen.queryByRole('textbox', { name: GROUP })).not.toBeInTheDocument()
    expect(group).toHaveAccessibleDescription(
      'This consumer group is fixed after the first publish so the subscription can resume from its committed offsets.'
    )
    expect(await axe(container)).toHaveNoViolations()
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ kafkaGroupId: 'published-group' }),
      expect.anything()
    )
    await user.type(screen.getByRole('textbox', { name: 'Topic' }), '.new')
    expect(screen.getByRole('textbox', { name: GROUP })).toBeEnabled()
    await user.clear(screen.getByRole('textbox', { name: 'Topic' }))
    await user.type(screen.getByRole('textbox', { name: 'Topic' }), 'orders')
    expect(screen.getByRole('group', { name: GROUP })).toHaveTextContent('published-group')
    expect(screen.queryByRole('textbox', { name: GROUP })).not.toBeInTheDocument()
  })

  it('preserves a draft replacement group while cached publication metadata refreshes', async () => {
    const source = {
      trigger_node_id: 'subscribe',
      source_id: 'source-1',
      generation: 1,
      configuration_revision: 1,
      group_id_is_generated: false,
      integration_id: initialData.integrationId,
      topic: 'orders',
      group_id: 'published-group',
    }
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: { kafka_subscription_sources: [source] },
      response: new Response(),
    })
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    const { client } = renderSettings({ existing: true, data: { kafkaGroupId: 'replacement-draft-group' }, onSubmit })
    await screen.findByRole('group', { name: GROUP })
    let finish: (() => void) | undefined
    vi.mocked(workflowFetchClient.GET).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = () =>
            resolve({
              data: {
                kafka_subscription_sources: [
                  { ...source, source_id: 'source-2', generation: 2, topic: 'other-session-topic' },
                ],
              },
              response: new Response(),
            })
        })
    )
    let refreshed: Promise<void> | undefined
    act(() => {
      refreshed = client.invalidateQueries({ queryKey: ['get', '/workflows/{workflow_id}'] })
    })
    expect(await screen.findByText('Checking published consumer groups…')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: GROUP })).toHaveValue('replacement-draft-group')
    expect(screen.getByRole('textbox', { name: GROUP })).toBeDisabled()
    await act(async () => {
      finish?.()
      await refreshed
    })
    await waitFor(() => expect(screen.getByRole('textbox', { name: GROUP })).toBeEnabled())
    expect(screen.getByRole('textbox', { name: GROUP })).toHaveValue('replacement-draft-group')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ kafkaGroupId: 'replacement-draft-group' }),
      expect.anything()
    )
  })

  it('keeps the group locked on a history failure and provides a working retry', async () => {
    vi.mocked(workflowFetchClient.GET).mockRejectedValue(new Error('Unavailable'))
    const user = userEvent.setup()
    renderSettings({ existing: true })
    expect(
      await screen.findByRole('heading', { name: 'Unable to check published consumer groups' })
    ).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: GROUP })).toBeDisabled()
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: { kafka_subscription_sources: [] },
      response: new Response(),
    })
    await user.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() => expect(screen.getByRole('textbox', { name: GROUP })).toBeEnabled())
  })
})
