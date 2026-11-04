import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { StepFormTabsLayout } from './StepFormTabsLayout'

describe('StepFormTabsLayout', () => {
  describe('tab navigation', () => {
    it('shows parameters content by default', () => {
      render(
        <StepFormTabsLayout
          parametersContent={<div>Parameter content</div>}
          settingsContent={<div>Settings content</div>}
        />
      )

      expect(screen.getByText('Parameter content')).toBeInTheDocument()
      expect(screen.queryByText('Settings content')).not.toBeInTheDocument()
    })

    it('switches to settings content when Settings tab is clicked', async () => {
      const user = userEvent.setup()
      render(
        <StepFormTabsLayout
          parametersContent={<div>Parameter content</div>}
          settingsContent={<div>Settings content</div>}
        />
      )

      await user.click(screen.getByRole('tab', { name: 'Settings' }))

      expect(screen.getByText('Settings content')).toBeInTheDocument()
      expect(screen.queryByText('Parameter content')).not.toBeInTheDocument()
    })

    it('does not render the Settings tab when settingsContent is not provided', () => {
      render(<StepFormTabsLayout parametersContent={<div>Parameter content</div>} />)

      expect(screen.queryByRole('tab', { name: 'Settings' })).not.toBeInTheDocument()
      expect(screen.getByText('Parameter content')).toBeInTheDocument()
    })
  })

  describe('settings tab visibility', () => {
    it('renders the Settings tab when settingsContent is provided', () => {
      render(
        <StepFormTabsLayout
          parametersContent={<div>Parameter content</div>}
          settingsContent={<div>Settings content</div>}
        />
      )

      expect(screen.getByRole('tab', { name: 'Settings' })).toBeInTheDocument()
      expect(screen.getByText('Parameter content')).toBeInTheDocument()
    })
  })

  describe('hideSettingsTab', () => {
    it('does not render the Settings tab when hideSettingsTab is true', () => {
      render(
        <StepFormTabsLayout
          parametersContent={<div>Parameter content</div>}
          settingsContent={<div>Settings content</div>}
          hideSettingsTab
        />
      )

      expect(screen.queryByRole('tab', { name: 'Settings' })).not.toBeInTheDocument()
      expect(screen.getByText('Parameter content')).toBeInTheDocument()
    })

    it('renders the Settings tab when hideSettingsTab is false', () => {
      render(
        <StepFormTabsLayout
          parametersContent={<div>Parameter content</div>}
          settingsContent={<div>Settings content</div>}
          hideSettingsTab={false}
        />
      )

      expect(screen.getByRole('tab', { name: 'Settings' })).toBeInTheDocument()
    })
  })
})
