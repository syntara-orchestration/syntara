import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { KafkaTransportFields } from './KafkaTransportFields'

function Wrapper() {
  const form = useForm({ defaultValues: { security_protocol: 'SASL_SSL', allow_plaintext: false } })
  return (
    <FormProvider {...form}>
      <KafkaTransportFields
        control={form.control}
        protocolName="security_protocol"
        plaintextName="allow_plaintext"
        fieldId="security-protocol"
      />
    </FormProvider>
  )
}

describe('KafkaTransportFields', () => {
  it('requires a separate explicit plaintext opt-in', async () => {
    const user = userEvent.setup()
    render(<Wrapper />)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Security protocol' }))
    await user.click(screen.getByRole('option', { name: /^PLAINTEXT/ }))
    const optIn = screen.getByRole('checkbox', { name: 'Allow unencrypted, unauthenticated connections' })
    expect(optIn).not.toBeChecked()
    await user.click(optIn)
    expect(optIn).toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Security protocol' }))
    await user.click(screen.getByRole('option', { name: /^SSL —/ }))
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('has no accessibility violations in plaintext mode', async () => {
    const user = userEvent.setup()
    const { container } = render(<Wrapper />)
    await user.click(screen.getByRole('button', { name: 'Security protocol' }))
    await user.click(screen.getByRole('option', { name: /^PLAINTEXT/ }))
    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })
})
