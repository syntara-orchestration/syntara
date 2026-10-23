import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { REACT_FLOW_VIEWPORT_EMPTY_STATE } from '../../constants/viewport'

import { SynEmptyStateViewportTooSmall } from './SynEmptyStateViewportTooSmall'

describe('SynEmptyStateViewportTooSmall', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<SynEmptyStateViewportTooSmall returnTo="/workflows" />)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders copy from viewport constants', () => {
    render(<SynEmptyStateViewportTooSmall returnTo="/workflows" />)

    expect(screen.getByRole('heading', { name: REACT_FLOW_VIEWPORT_EMPTY_STATE.title })).toBeInTheDocument()
    expect(screen.getByText(REACT_FLOW_VIEWPORT_EMPTY_STATE.body)).toBeInTheDocument()
  })

  it('renders the return destination as a link', () => {
    render(<SynEmptyStateViewportTooSmall returnTo="/workflows" />)

    expect(screen.getByRole('link', { name: REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel })).toHaveAttribute(
      'href',
      '/workflows'
    )
  })
})
