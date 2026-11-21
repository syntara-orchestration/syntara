import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { useTriggerRemovalPublishConfirm } from './useTriggerRemovalPublishConfirm'

function Harness({ error, onRetry }: Readonly<{ error: unknown; onRetry: () => void }>) {
  const { guardPublishError, triggerRemovalConfirmDialog } = useTriggerRemovalPublishConfirm()
  return (
    <>
      <button type="button" onClick={() => guardPublishError(error, onRetry)}>
        guard
      </button>
      {triggerRemovalConfirmDialog}
    </>
  )
}

const confirmationError = {
  cause: { code: 'WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED', affected_count: 2 },
}

describe('useTriggerRemovalPublishConfirm', () => {
  it('opens a confirm dialog on the trigger-removal 409 and retries on confirm', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<Harness error={confirmationError} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'guard' }))

    expect(screen.getByText(/used by 2 published workflow\(s\)/)).toBeInTheDocument()
    expect(onRetry).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Publish anyway' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('ignores unrelated errors and does not retry', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<Harness error={{ code: 'OTHER' }} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'guard' }))

    expect(screen.queryByText(/used by/)).not.toBeInTheDocument()
    expect(onRetry).not.toHaveBeenCalled()
  })
})
