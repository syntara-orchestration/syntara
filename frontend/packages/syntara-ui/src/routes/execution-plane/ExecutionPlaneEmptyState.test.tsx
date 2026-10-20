import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ExecutionPlaneEmptyState } from './ExecutionPlaneEmptyState'

describe('ExecutionPlaneEmptyState', () => {
  it('has no accessibility violations when configure action is shown', async () => {
    const { container } = render(<ExecutionPlaneEmptyState canConfigure />)

    expect(screen.getByRole('button', { name: 'Configure integration' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when configure action is hidden', async () => {
    const { container } = render(<ExecutionPlaneEmptyState canConfigure={false} />)

    expect(screen.queryByRole('button', { name: 'Configure integration' })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
