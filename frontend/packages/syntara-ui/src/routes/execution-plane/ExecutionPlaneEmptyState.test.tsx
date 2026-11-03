import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { AppRoute } from '../../app/AppRoute'
import { routerTestState } from '../../test/setup'

import { ExecutionPlaneEmptyState } from './ExecutionPlaneEmptyState'

describe('ExecutionPlaneEmptyState', () => {
  beforeEach(() => {
    routerTestState.navigate.mockClear()
  })

  it('defaults to showing the configure action', () => {
    render(<ExecutionPlaneEmptyState />)

    expect(screen.getByRole('button', { name: 'Configure integration' })).toBeInTheDocument()
  })

  it('navigates to configure integration when the button is clicked', async () => {
    const user = userEvent.setup()
    render(<ExecutionPlaneEmptyState canConfigure />)

    await user.click(screen.getByRole('button', { name: 'Configure integration' }))

    expect(routerTestState.navigate).toHaveBeenCalledWith(
      expect.objectContaining({ to: AppRoute.Configuration.Integrations.Configure })
    )
  })

  it('hides the configure action when canConfigure is false', () => {
    render(<ExecutionPlaneEmptyState canConfigure={false} />)

    expect(screen.queryByRole('button', { name: 'Configure integration' })).not.toBeInTheDocument()
  })

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
