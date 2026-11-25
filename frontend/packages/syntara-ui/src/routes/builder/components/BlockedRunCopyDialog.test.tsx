import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BlockedRunCopyDialog } from './BlockedRunCopyDialog'

function renderDialog(overrides: Partial<React.ComponentProps<typeof BlockedRunCopyDialog>> = {}) {
  const props: React.ComponentProps<typeof BlockedRunCopyDialog> = {
    blockedRunCopy: { labels: ['Script', 'HTTP Request'], losesAllTriggers: false },
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  }
  return { ...render(<BlockedRunCopyDialog {...props} />), props }
}

describe('BlockedRunCopyDialog', () => {
  it('does not render without a blocked copy', () => {
    renderDialog({ blockedRunCopy: null })

    expect(screen.queryByText("Some steps can't be copied")).not.toBeInTheDocument()
  })

  it('names the blocked step types', () => {
    renderDialog()

    expect(screen.getByText("Some steps can't be copied")).toBeInTheDocument()
    expect(
      screen.getByText(
        "You don't have permission to write these step types: Script, HTTP Request. Copy the run without those steps?"
      )
    ).toBeInTheDocument()
  })

  it('says the connections to the left-out steps will be removed', () => {
    renderDialog()

    expect(
      screen.getByText(
        'Connections to those steps will be removed. Review and reconnect the affected steps after copying.'
      )
    ).toBeInTheDocument()
  })

  it('does not mention triggers when a trigger will be copied', () => {
    renderDialog()

    expect(screen.queryByText(/No trigger will be copied/)).not.toBeInTheDocument()
  })

  it('warns when no trigger will be copied', () => {
    renderDialog({ blockedRunCopy: { labels: ['Manual trigger'], losesAllTriggers: true } })

    expect(
      screen.getByText('No trigger will be copied. Add a permitted trigger before running this workflow.')
    ).toBeInTheDocument()
  })

  it('confirms the copy without the blocked steps', async () => {
    const { props } = renderDialog()

    await userEvent.click(screen.getByRole('button', { name: 'Copy without those steps' }))

    expect(props.onConfirm).toHaveBeenCalledOnce()
    expect(props.onCancel).not.toHaveBeenCalled()
  })

  it('cancels the copy', async () => {
    const { props } = renderDialog()

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(props.onCancel).toHaveBeenCalledOnce()
    expect(props.onConfirm).not.toHaveBeenCalled()
  })
})
