import { Button } from '@patternfly/react-core'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { KafkaCredentialConnection } from './KafkaCredentialConnection'
import styles from './KafkaCredentialConnection.module.css'

function renderConnection(props = {}) {
  return render(
    <KafkaCredentialConnection isPending={false} isDisabled={false} {...props}>
      {(onSelected) => <Button onClick={onSelected}>Choose credential</Button>}
    </KafkaCredentialConnection>
  )
}

describe('Kafka credential connection', () => {
  it.each([
    { credentialName: undefined, errorMessage: undefined },
    { credentialName: 'Invalid saved credential', errorMessage: 'Select an available credential' },
  ])('shows a decorative warning for missing or invalid credentials: %j', async (props) => {
    const { container } = renderConnection(props)
    expect(screen.getByText('Kafka runtime credential not configured')).toBeInTheDocument()
    const icon = within(screen.getByTestId('icon-label')).getByRole('img', { hidden: true })
    expect(icon).toHaveClass(styles.warningIcon)
    expect(icon).toHaveAttribute('aria-hidden', 'true')
    expect(await axe(container)).toHaveNoViolations()
  })

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
    expect(screen.getByText('Orders runtime')).toBeInTheDocument()
    expect(screen.queryByText(/Kafka runtime credential:/)).not.toBeInTheDocument()
    expect(within(screen.getByTestId('icon-label')).getByRole('img', { hidden: true })).toHaveClass(styles.checkIcon)
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
    expect(screen.getByText('Orders runtime')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change' })).toHaveFocus()
  })

  it('does not offer editing in read-only views', () => {
    renderConnection({ credentialName: 'Orders runtime', isDisabled: true })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows optional credential setup without a warning when authentication is not required', async () => {
    const { container } = renderConnection({ isRequired: false, isCompact: true, credentialLabel: 'Kafka credential' })

    expect(screen.getByText('Kafka credential optional')).toBeInTheDocument()
    expect(screen.queryByRole('img', { hidden: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Set up connection' })).toBeEnabled()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('waits for credential queries before allowing setup', () => {
    renderConnection({ isPending: true })
    expect(screen.getByRole('button', { name: 'Set up connection' })).toBeDisabled()
    expect(screen.queryByRole('img', { hidden: true })).not.toBeInTheDocument()
  })

  it('restores focus after the selected credential finishes loading', async () => {
    const user = userEvent.setup()
    const { rerender } = renderConnection()
    await user.click(screen.getByRole('button', { name: 'Set up connection' }))
    rerender(
      <KafkaCredentialConnection isPending isDisabled={false}>
        {(onSelected) => <Button onClick={onSelected}>Choose credential</Button>}
      </KafkaCredentialConnection>
    )
    await user.click(screen.getByRole('button', { name: 'Choose credential' }))
    expect(screen.queryByRole('button', { name: 'Choose credential' })).not.toBeInTheDocument()
    rerender(
      <KafkaCredentialConnection credentialName="Orders runtime" isPending={false} isDisabled={false}>
        {(onSelected) => <Button onClick={onSelected}>Choose credential</Button>}
      </KafkaCredentialConnection>
    )
    expect(screen.getByRole('button', { name: 'Change' })).toHaveFocus()
  })
})
