import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BlockedForkDialog } from './BlockedForkDialog'

function renderDialog(overrides: Partial<React.ComponentProps<typeof BlockedForkDialog>> = {}) {
  const props: React.ComponentProps<typeof BlockedForkDialog> = {
    blockedFork: { labels: ['Script', 'HTTP Request'], losesAllTriggers: false },
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  }
  return { ...render(<BlockedForkDialog {...props} />), props }
}

describe('BlockedForkDialog', () => {
  it('does not render without a blocked fork', () => {
    renderDialog({ blockedFork: null })

    expect(screen.queryByText("Some steps can't be forked")).not.toBeInTheDocument()
  })

  it('names the blocked step types and says connections will be removed', () => {
    renderDialog()

    expect(screen.getByText("Some steps can't be forked")).toBeInTheDocument()
    expect(
      screen.getByText(
        "You don't have permission to write these step types: Script, HTTP Request. Fork the run without those steps?"
      )
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'Connections to those steps will be removed. Review and reconnect the affected steps after forking.'
      )
    ).toBeInTheDocument()
    expect(screen.queryByText(/No trigger will be copied/)).not.toBeInTheDocument()
  })

  it('warns when no trigger survives', () => {
    renderDialog({ blockedFork: { labels: ['Webhook'], losesAllTriggers: true } })

    expect(
      screen.getByText('No trigger will be copied. Add a permitted trigger before running this workflow.')
    ).toBeInTheDocument()
  })

  it('confirms and cancels', async () => {
    const user = userEvent.setup()
    const { props } = renderDialog()

    await user.click(screen.getByRole('button', { name: 'Fork without those steps' }))
    expect(props.onConfirm).toHaveBeenCalledOnce()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(props.onCancel).toHaveBeenCalled()
  })
})
