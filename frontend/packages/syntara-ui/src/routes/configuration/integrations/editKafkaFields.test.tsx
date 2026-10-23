import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm, type UseFormReturn } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynForm } from '../../../components/forms/SynForm'

import type { EditIntegrationFormValues } from './editIntegrationFormSchema'
import { EditKafkaFields } from './editKafkaFields'

function KafkaFieldsHarness({
  errorMessage,
  bootstrapServers,
  saslMechanism = 'SCRAM-SHA-256',
}: Readonly<{
  errorMessage?: string
  bootstrapServers?: string
  saslMechanism?: string
}>) {
  const form: UseFormReturn<EditIntegrationFormValues> = useForm<EditIntegrationFormValues>({
    defaultValues: {
      name: 'Production Kafka',
      description: '',
      integration_type: 'kafka',
      bootstrap_servers: bootstrapServers,
      sasl_mechanism: saslMechanism as EditIntegrationFormValues['sasl_mechanism'],
      allow_http: false,
      insecure_skip_tls_verify: false,
      ca_certificate: null,
      scope: 'global',
      project_ids: [],
      management_credential_id: null,
    },
  })

  return (
    <SynForm form={form}>
      <EditKafkaFields control={form.control} errorMessage={errorMessage} />
    </SynForm>
  )
}

describe('EditKafkaFields', () => {
  it('shows the broker list and the current SASL mechanism', () => {
    render(<KafkaFieldsHarness bootstrapServers={'broker.example.com:9093\nother.example.com:9092'} />)

    expect(screen.getByRole('textbox', { name: 'Bootstrap servers' })).toHaveValue(
      'broker.example.com:9093\nother.example.com:9092'
    )
    expect(screen.getByText('SCRAM-SHA-256')).toBeInTheDocument()
    expect(screen.queryByText(/at least one bootstrap server/i)).not.toBeInTheDocument()
  })

  it('shows an empty broker list when the stored value is missing', () => {
    render(<KafkaFieldsHarness />)

    expect(screen.getByRole('textbox', { name: 'Bootstrap servers' })).toHaveValue('')
  })

  it('shows the raw mechanism when it is not one of the known options', () => {
    render(<KafkaFieldsHarness saslMechanism="GSSAPI" />)

    expect(screen.getByText('GSSAPI')).toBeInTheDocument()
  })

  it('updates the broker list and reports the validation error', async () => {
    const user = userEvent.setup()
    render(<KafkaFieldsHarness errorMessage="At least one bootstrap server is required" />)

    const brokers = screen.getByRole('textbox', { name: 'Bootstrap servers' })
    expect(screen.getByText('At least one bootstrap server is required')).toBeInTheDocument()

    await user.type(brokers, 'broker.example.com:9093')
    expect(brokers).toHaveValue('broker.example.com:9093')

    brokers.blur()
    expect(brokers).not.toHaveFocus()
  })

  it('changes the SASL mechanism', async () => {
    const user = userEvent.setup()
    render(<KafkaFieldsHarness />)

    await user.click(screen.getByText('SCRAM-SHA-256'))
    await user.click(screen.getByRole('option', { name: 'PLAIN' }))

    expect(screen.getByText('PLAIN')).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'SCRAM-SHA-512' })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <KafkaFieldsHarness
        bootstrapServers="broker.example.com:9093"
        errorMessage="At least one bootstrap server is required"
      />
    )

    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })
})
