import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { DRAG_TYPE_FIELD } from '../../../components/expressions/expressionFieldDrag'
import { renderWithForm } from '../../../test/renderWithForm'
import { VersionViewContext } from '../VersionViewContext'

import { kafkaPublishFormSchema, type KafkaPublishFormData } from './kafkaPublishFormSchema'
import { KafkaPublishMessageFields } from './KafkaPublishMessageFields'

const defaults: KafkaPublishFormData = {
  name: 'Publish',
  integration_id: '11111111-1111-4111-8111-111111111111',
  credential_id: '22222222-2222-4222-8222-222222222222',
  connection_ready: true,
  topic: 'outcomes',
  payload: '{}',
  key: { encoding: 'null', value: '' },
  headers_mode: 'entries',
  headers: [{ name: 'same', encoding: 'utf-8', value: 'first' }],
  headers_template: '',
  settings: {},
}

function setup(initial: Partial<KafkaPublishFormData> = {}, readOnly = false) {
  const onSubmit = vi.fn()
  const view = renderWithForm(
    { schema: kafkaPublishFormSchema, defaultValues: { ...defaults, ...initial } },
    (form) => (
      <VersionViewContext value={readOnly}>
        <FormProvider {...form}>
          <KafkaPublishMessageFields />
          <button type="button" onClick={form.handleSubmit(onSubmit)}>
            Save
          </button>
        </FormProvider>
      </VersionViewContext>
    )
  )
  return { ...view, onSubmit, user: userEvent.setup() }
}

describe('Kafka Publish prototype message controls', () => {
  it.each([
    ['utf-8', 'Enter a message key value'],
    ['base64', 'Enter a Base64-encoded value'],
  ] as const)('uses the %s placeholder without losing an empty value', async (encoding, placeholder) => {
    const { user, onSubmit } = setup({ key: { encoding, value: '' } })
    const value = screen.getByRole('textbox', { name: 'Message key value' })
    expect(value).toHaveAttribute('placeholder', placeholder)
    expect(value).toHaveAttribute('rows', '1')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ key: { encoding, value: '' } }),
        expect.anything()
      )
    )
  })

  it('hides the value for a null key and explains the byte representations in field help', async () => {
    const { user } = setup()
    expect(screen.queryByRole('textbox', { name: 'Message key value' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'More info for Message key encoding' }))
    expect(await screen.findByRole('dialog', { name: 'Message key encoding' })).toHaveTextContent(
      'Null sends no bytes. An empty UTF-8 or Base64 value sends an empty byte sequence.'
    )
  })

  it('keeps multiline UTF-8 text intact in the compact value field', async () => {
    const { user, onSubmit } = setup({ key: { encoding: 'utf-8', value: 'first\nsecond' } })
    expect(screen.getByRole('textbox', { name: 'Message key value' })).toHaveValue('first\nsecond')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ key: { encoding: 'utf-8', value: 'first\nsecond' } }),
        expect.anything()
      )
    )
  })

  it('accepts a dragged workflow expression for the key without templating the destination', async () => {
    const { user, onSubmit } = setup({ key: { encoding: 'utf-8', value: '' } })
    fireEvent.drop(screen.getByRole('textbox', { name: 'Message key value' }), {
      dataTransfer: {
        getData: () => JSON.stringify({ type: DRAG_TYPE_FIELD, nodeId: 'trigger', fieldPath: ['order_id'] }),
      },
    })
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          topic: 'outcomes',
          key: { encoding: 'utf-8', value: '${trigger.order_id}' },
        }),
        expect.anything()
      )
    )
  })

  it('collapses a header without discarding its value and preserves toggle focus', async () => {
    const { user, container, onSubmit } = setup()
    const toggle = screen.getByRole('button', { name: 'Collapse header 1' })
    await user.click(toggle)
    expect(toggle).toHaveFocus()
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('textbox', { name: 'Header 1 value' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Header 1 name' })).toHaveValue('same')
    await user.click(screen.getByRole('button', { name: 'Expand header 1' }))
    expect(screen.getByRole('textbox', { name: 'Header 1 value' })).toHaveValue('first')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ headers: defaults.headers }), expect.anything())
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('offers concise header guidance and help in both modes', async () => {
    const { user } = setup()
    expect(screen.getByText('Configure headers sent with each Kafka message.')).toBeVisible()
    expect(screen.queryByText(/Maximum 128 entries/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Message headers help' }))
    expect(await screen.findByRole('dialog', { name: 'Message headers help' })).toHaveTextContent(
      'Headers are sent in the order shown, and duplicate names are allowed. A null value sends no bytes; an empty value sends an empty byte sequence. You can add up to 128 headers and drag entries to reorder them.'
    )
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'Header source' }))
    await user.click(screen.getByRole('option', { name: 'Full-value template' }))
    expect(screen.getByText('Configure headers sent with each Kafka message.')).toBeVisible()
    expect(screen.getByRole('textbox', { name: 'Headers template' })).toBeVisible()
    expect(
      screen.getByText(
        'Use a full-value template, such as ${trigger.payload.headers}, that resolves to an ordered list of header entries.'
      )
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'More info for Header source' }))
    expect(await screen.findByRole('dialog', { name: 'Header source' })).toHaveTextContent(
      "Ordered entries: Configure each header's name, encoding, and value."
    )
    expect(screen.getByRole('dialog', { name: 'Header source' })).toHaveTextContent(
      'Full-value template: Provide one expression that resolves to an ordered list of headers.'
    )
    expect(screen.getByText('Ordered entries:', { exact: true }).tagName).toBe('STRONG')
    expect(screen.getByText('Full-value template:', { exact: true }).tagName).toBe('STRONG')
  })

  it.each([0, 1, 2])('shows the reorder cue only when reordering is possible: %s headers', (count) => {
    setup({ headers: Array.from({ length: count }, () => ({ name: 'same', encoding: 'utf-8', value: '' })) })
    if (count > 1) expect(screen.getByText('Drag to reorder headers.')).toBeVisible()
    else expect(screen.queryByText('Drag to reorder headers.')).not.toBeInTheDocument()
  })

  it('removes the reorder cue and returns focus to Add header after the last header is removed', async () => {
    const { user } = setup({ headers: [defaults.headers[0], defaults.headers[0]] })
    expect(screen.getByText('Drag to reorder headers.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Remove header 2' }))
    expect(screen.queryByText('Drag to reorder headers.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove header 1' }))
    expect(screen.getByRole('button', { name: 'Add header' })).toHaveFocus()
    expect(screen.queryByRole('group', { name: /Header \d/ })).not.toBeInTheDocument()
  })

  it('allows expanding read-only headers while preventing edits and drops', async () => {
    const { user } = setup({ key: { encoding: 'utf-8', value: 'saved' } }, true)
    expect(screen.getByRole('textbox', { name: 'Message key value' })).toBeDisabled()
    fireEvent.drop(screen.getByRole('textbox', { name: 'Message key value' }), {
      dataTransfer: {
        getData: () => JSON.stringify({ type: DRAG_TYPE_FIELD, nodeId: 'trigger', fieldPath: ['order_id'] }),
      },
    })
    expect(screen.getByRole('textbox', { name: 'Message key value' })).toHaveValue('saved')
    await user.click(screen.getByRole('button', { name: 'Collapse header 1' }))
    await user.click(screen.getByRole('button', { name: 'Expand header 1' }))
    expect(screen.getByRole('textbox', { name: 'Header 1 value' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Remove header 1' })).not.toBeInTheDocument()
  })
})
