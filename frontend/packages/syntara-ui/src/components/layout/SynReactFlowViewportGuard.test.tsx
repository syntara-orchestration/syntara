import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { AppRoute } from '../../app/AppRoute'
import { REACT_FLOW_VIEWPORT_EMPTY_STATE } from '../../constants/viewport'
import { routerTestState } from '../../test/setup'

import { SynReactFlowViewportGuard } from './SynReactFlowViewportGuard'

describe('SynReactFlowViewportGuard', () => {
  beforeEach(() => {
    routerTestState.navigate.mockClear()
  })

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

  it('navigates to workflows when Return to Workflows is clicked', async () => {
    const user = userEvent.setup()

    render(
      <SynReactFlowViewportGuard>
        <div>Workflow canvas</div>
      </SynReactFlowViewportGuard>
    )

    const returnButton = screen.getByRole('button', {
      name: REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel,
      hidden: true,
    })
    await user.click(returnButton)

    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: AppRoute.Workflows.Root })
  })

  it('navigates to custom destination when onReturn callback is provided', async () => {
    const user = userEvent.setup()
    const customReturn = vi.fn()

    render(
      <SynReactFlowViewportGuard onReturn={customReturn}>
        <div>Workflow canvas</div>
      </SynReactFlowViewportGuard>
    )

    const returnButton = screen.getByRole('button', {
      name: REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel,
      hidden: true,
    })
    await user.click(returnButton)

    expect(customReturn).toHaveBeenCalledTimes(1)
    expect(routerTestState.navigate).not.toHaveBeenCalled()
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
