import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { useReferencedDeleteConfirm } from './useReferencedDeleteConfirm'

function Harness({ error, onRetry }: Readonly<{ error: unknown; onRetry: () => void }>) {
  const { guardDeleteError, referencedDeleteConfirmDialog } = useReferencedDeleteConfirm()
  return (
    <>
      <button type="button" onClick={() => guardDeleteError(error, onRetry)}>
        guard
      </button>
      {referencedDeleteConfirmDialog}
    </>
  )
}

const confirmationError = {
  cause: { code: 'WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED', referencing_count: 3 },
}

describe('useReferencedDeleteConfirm', () => {
  it('opens a confirm dialog on the referenced 409 and retries on confirm', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<Harness error={confirmationError} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'guard' }))

    expect(screen.getByText(/used as a sub-workflow by 3 published workflow\(s\)/)).toBeInTheDocument()
    expect(onRetry).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Delete anyway' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('cancelling the dialog does not retry', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<Harness error={confirmationError} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'guard' }))
    expect(screen.getByRole('button', { name: 'Delete anyway' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onRetry).not.toHaveBeenCalled()
    expect(screen.queryByText(/used as a sub-workflow by/)).not.toBeInTheDocument()
  })

  it('does not open the dialog or retry on a malformed confirmation (missing count)', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<Harness error={{ cause: { code: 'WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED' } }} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'guard' }))

    expect(screen.queryByRole('button', { name: 'Delete anyway' })).not.toBeInTheDocument()
    expect(onRetry).not.toHaveBeenCalled()
  })

  it('ignores unrelated errors and does not retry', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<Harness error={{ code: 'OTHER' }} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'guard' }))

    expect(screen.queryByText(/used as a sub-workflow by/)).not.toBeInTheDocument()
    expect(onRetry).not.toHaveBeenCalled()
  })
})
