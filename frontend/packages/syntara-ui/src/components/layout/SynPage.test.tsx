import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynPage, SynPageBody } from './SynPage'

describe('SynPage', () => {
  it('renders children', () => {
    render(
      <SynPage>
        <div data-testid="child">Child Content</div>
      </SynPage>
    )

    expect(screen.getByTestId('child')).toBeInTheDocument()
    expect(screen.getByText('Child Content')).toBeInTheDocument()
  })

  it('renders multiple children', () => {
    render(
      <SynPage>
        <div data-testid="child1">First</div>
        <div data-testid="child2">Second</div>
        <div data-testid="child3">Third</div>
      </SynPage>
    )

    expect(screen.getByTestId('child1')).toBeInTheDocument()
    expect(screen.getByTestId('child2')).toBeInTheDocument()
    expect(screen.getByTestId('child3')).toBeInTheDocument()
  })

  it('SynPageBody renders a filled stack item for main column content', () => {
    render(
      <SynPage>
        <SynPageBody data-testid="app-page-main">
          <div data-testid="main-region">Main</div>
        </SynPageBody>
      </SynPage>
    )

    expect(screen.getByTestId('main-region')).toBeInTheDocument()
    expect(screen.getByTestId('app-page-main')).toHaveClass('pf-m-fill')
  })

  it('SynPageBody applies centered flex layout when isCentered is set', () => {
    render(
      <SynPage>
        <SynPageBody data-testid="app-page-main" isCentered>
          <div>Centered</div>
        </SynPageBody>
      </SynPage>
    )

    expect(screen.getByTestId('app-page-main')).toHaveStyle({
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations when SynPage wraps SynPageBody', async () => {
      const { container } = render(
        <SynPage>
          <SynPageBody>
            <main>
              <h1>Page title</h1>
              <p>Body</p>
            </main>
          </SynPageBody>
        </SynPage>
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
