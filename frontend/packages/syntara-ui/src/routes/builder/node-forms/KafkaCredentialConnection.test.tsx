import { Button } from '@patternfly/react-core'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { KafkaCredentialConnection } from './KafkaCredentialConnection'

function renderConnection(props = {}) {
  return render(
    <KafkaCredentialConnection isPending={false} isDisabled={false} {...props}>
      {(onSelected) => <Button onClick={onSelected}>Choose credential</Button>}
    </KafkaCredentialConnection>
  )
}

describe('Kafka credential connection', () => {
  it('opens setup on demand and restores focus after choosing a credential', async () => {
    const user = userEvent.setup()
    const { container } = renderConnection()
    expect(screen.queryByRole('button', { name: 'Choose credential' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Set up connection' }))
    await user.click(screen.getByRole('button', { name: 'Choose credential' }))
    expect(screen.queryByRole('button', { name: 'Choose credential' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Set up connection' })).toHaveFocus()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows the configured credential and Change without claiming verified broker access', async () => {
    const user = userEvent.setup()
    renderConnection({ credentialName: 'Orders runtime' })
    expect(screen.getByText('Kafka runtime credential: Orders runtime')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Change' }))
    await user.click(screen.getByRole('button', { name: 'Choose credential' }))
    expect(screen.getByRole('button', { name: 'Change' })).toHaveFocus()
  })

  it('associates the saved credential error with setup until the picker opens', async () => {
    const user = userEvent.setup()
    renderConnection({ credentialName: 'Invalid credential', errorMessage: 'Select an available Kafka credential' })
    expect(screen.getByText('Select an available Kafka credential')).toBeInTheDocument()
    const setup = screen.getByRole('button', { name: 'Set up connection' })
    expect(setup).toHaveAccessibleDescription(/Select an available Kafka credential/)
    await user.click(setup)
    expect(screen.getByRole('button', { name: 'Cancel' })).not.toHaveAttribute('aria-describedby')
  })

  it('preserves the configured credential when setup is cancelled and restores focus', async () => {
    const user = userEvent.setup()
    renderConnection({ credentialName: 'Orders runtime' })
    await user.click(screen.getByRole('button', { name: 'Change' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('button', { name: 'Choose credential' })).not.toBeInTheDocument()
    expect(screen.getByText('Kafka runtime credential: Orders runtime')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change' })).toHaveFocus()
  })

  it('does not offer editing in read-only views', () => {
    renderConnection({ credentialName: 'Orders runtime', isDisabled: true })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('waits for credential queries before allowing setup', () => {
    renderConnection({ isPending: true })
    expect(screen.getByRole('button', { name: 'Set up connection' })).toBeDisabled()
  })
})
