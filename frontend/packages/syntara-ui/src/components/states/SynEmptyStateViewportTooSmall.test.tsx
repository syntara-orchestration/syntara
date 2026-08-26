import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { REACT_FLOW_VIEWPORT_EMPTY_STATE } from '../../constants/viewport'

import { SynEmptyStateViewportTooSmall } from './SynEmptyStateViewportTooSmall'

describe('SynEmptyStateViewportTooSmall', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<SynEmptyStateViewportTooSmall onReturn={vi.fn()} />)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders copy from viewport constants', () => {
    render(<SynEmptyStateViewportTooSmall onReturn={vi.fn()} />)

    expect(screen.getByRole('heading', { name: REACT_FLOW_VIEWPORT_EMPTY_STATE.title })).toBeInTheDocument()
    expect(screen.getByText(REACT_FLOW_VIEWPORT_EMPTY_STATE.body)).toBeInTheDocument()
  })

  it('calls onReturn when the primary action is clicked', async () => {
    const user = userEvent.setup()
    const onReturn = vi.fn()

    render(<SynEmptyStateViewportTooSmall onReturn={onReturn} />)
    await user.click(screen.getByRole('button', { name: REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel }))

    expect(onReturn).toHaveBeenCalledOnce()
  })
})
