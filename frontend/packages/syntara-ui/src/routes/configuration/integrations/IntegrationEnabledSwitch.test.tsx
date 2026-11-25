import type { IntegrationsAPI } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { IntegrationEnabledSwitch } from './IntegrationEnabledSwitch'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

const integration = {
  id: 'int-1',
  name: 'My Server',
  enabled: true,
} as IntegrationRead

describe('IntegrationEnabledSwitch', () => {
  it('renders an interactive switch when the user can update', async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()

    render(
      <IntegrationEnabledSwitch
        integration={integration}
        switchId="toggle-1"
        canUpdate
        isPermissionsLoading={false}
        updateDeniedTooltip="No permission"
        onToggle={onToggle}
      />
    )

    const toggle = screen.getByRole('switch', { name: /toggle my server/i })
    expect(toggle).toBeChecked()
    expect(toggle).toBeEnabled()

    await user.click(toggle)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('disables the switch and shows a permission tooltip when update is denied', async () => {
    const user = userEvent.setup()

    render(
      <IntegrationEnabledSwitch
        integration={integration}
        switchId="toggle-1"
        canUpdate={false}
        isPermissionsLoading={false}
        updateDeniedTooltip="No permission to enable"
        onToggle={vi.fn()}
      />
    )

    const toggle = screen.getByRole('switch', { name: /toggle my server/i })
    expect(toggle).toBeDisabled()

    await user.hover(toggle)
    expect(await screen.findByText('No permission to enable')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <IntegrationEnabledSwitch
        integration={integration}
        switchId="toggle-1"
        canUpdate
        isPermissionsLoading={false}
        updateDeniedTooltip="No permission"
        onToggle={vi.fn()}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
