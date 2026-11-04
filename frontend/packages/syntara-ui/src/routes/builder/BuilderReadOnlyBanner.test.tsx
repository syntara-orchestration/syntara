import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { BuilderReadOnlyBanner } from './BuilderReadOnlyBanner'

describe('BuilderReadOnlyBanner', () => {
  it('renders nothing when canEdit is true', () => {
    const { container } = render(<BuilderReadOnlyBanner canEdit={true} isLoading={false} isBuiltin={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when isLoading is true', () => {
    const { container } = render(<BuilderReadOnlyBanner canEdit={false} isLoading={true} isBuiltin={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders builtin title when isBuiltin is true', () => {
    render(<BuilderReadOnlyBanner canEdit={false} isLoading={false} isBuiltin={true} />)
    expect(screen.getByText('This is a built-in workflow.')).toBeInTheDocument()
  })

  it('renders builtin body text when isBuiltin is true', () => {
    render(<BuilderReadOnlyBanner canEdit={false} isLoading={false} isBuiltin={true} />)
    expect(screen.getByText('Built-in workflows cannot be modified.')).toBeInTheDocument()
  })

  it('renders read-only title when not builtin and cannot edit', () => {
    render(<BuilderReadOnlyBanner canEdit={false} isLoading={false} isBuiltin={false} />)
    expect(screen.getByText('You are viewing this workflow in read-only mode.')).toBeInTheDocument()
  })

  it('renders permission body text when not builtin and cannot edit', () => {
    render(<BuilderReadOnlyBanner canEdit={false} isLoading={false} isBuiltin={false} />)
    expect(
      screen.getByText(
        'You do not have permission to edit this workflow. Contact your administrator to request access.'
      )
    ).toBeInTheDocument()
  })

  it('lists blocked step display names without policy details', () => {
    render(
      <BuilderReadOnlyBanner
        canEdit={false}
        isLoading={false}
        isBuiltin={false}
        blockedStepTypes={['Script', 'REST API']}
      />
    )

    expect(screen.getByText('You are viewing this workflow in read-only mode.')).toBeInTheDocument()
    expect(screen.getByText('Blocked step types: Script, REST API.')).toBeInTheDocument()
    expect(screen.queryByText(/policy|scope/i)).not.toBeInTheDocument()
  })

  it('offers a retry action when permission checks fail', async () => {
    const user = userEvent.setup()
    const onRetryPermissionCheck = vi.fn()
    render(
      <BuilderReadOnlyBanner
        canEdit={false}
        isLoading={false}
        isBuiltin={false}
        permissionCheckError
        onRetryPermissionCheck={onRetryPermissionCheck}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Retry permission check' }))

    expect(onRetryPermissionCheck).toHaveBeenCalledOnce()
  })

  it('has no accessibility violations when showing builtin banner', async () => {
    const { container } = render(<BuilderReadOnlyBanner canEdit={false} isLoading={false} isBuiltin={true} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when showing read-only banner', async () => {
    const { container } = render(<BuilderReadOnlyBanner canEdit={false} isLoading={false} isBuiltin={false} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
