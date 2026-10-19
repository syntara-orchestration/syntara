import { render, screen, within } from '@testing-library/react'
import { axe } from 'vitest-axe'

import { AppRoute } from '../../app/AppRoute'
import { REACT_FLOW_VIEWPORT_EMPTY_STATE } from '../../constants/viewport'

import { SynReactFlowViewportGuard } from './SynReactFlowViewportGuard'

describe('SynReactFlowViewportGuard', () => {
  it('renders canvas content at supported viewport sizes', () => {
    render(
      <SynReactFlowViewportGuard>
        <div>Workflow canvas</div>
      </SynReactFlowViewportGuard>
    )

    expect(screen.getByText('Workflow canvas')).toBeInTheDocument()
    // Both branches are always in the DOM; CSS hides one based on viewport size.
    // Verify the empty-state heading lives inside the CSS-hidden branch (data-testid
    // marks the StackItem that display:none hides at supported viewport sizes).
    const emptyStateSection = screen.getByTestId('viewport-guard-empty-state')
    expect(
      within(emptyStateSection).getByRole('heading', {
        name: REACT_FLOW_VIEWPORT_EMPTY_STATE.title,
        hidden: true,
      })
    ).toBeInTheDocument()
  })

  it('links to workflows by default', () => {
    render(
      <SynReactFlowViewportGuard>
        <div>Workflow canvas</div>
      </SynReactFlowViewportGuard>
    )

    const returnLink = screen.getByRole('link', {
      name: REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel,
      hidden: true,
    })
    expect(returnLink).toHaveAttribute('href', AppRoute.Workflows.Root)
  })

  it('links to a custom destination', () => {
    render(
      <SynReactFlowViewportGuard returnTo="/executions">
        <div>Workflow canvas</div>
      </SynReactFlowViewportGuard>
    )

    const returnLink = screen.getByRole('link', {
      name: REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel,
      hidden: true,
    })
    expect(returnLink).toHaveAttribute('href', '/executions')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <SynReactFlowViewportGuard>
        <div>Workflow canvas</div>
      </SynReactFlowViewportGuard>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
