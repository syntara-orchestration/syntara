import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynPanelContentStack } from './SynPanelContentStack'

describe('SynPanelContentStack', () => {
  it('renders children with default panel stack styles', () => {
    render(
      <SynPanelContentStack>
        <div>Main</div>
      </SynPanelContentStack>
    )

    const child = screen.getByText('Main')
    /* eslint-disable testing-library/no-node-access -- Stack is a layout div with no role; assert styles on the PF wrapper (testing guideline prefer queries first on children). */
    expect(child.parentElement).toHaveStyle({
      height: '100%',
      flexGrow: 1,
      minHeight: '0px',
    })
    /* eslint-enable testing-library/no-node-access */
  })

  it('renders inset variant with horizontal padding token', () => {
    render(
      <SynPanelContentStack variant="inset">
        <span>List</span>
      </SynPanelContentStack>
    )

    const child = screen.getByText('List')
    /* eslint-disable testing-library/no-node-access -- Stack root has no accessible role; style + padding token checked via parent of known text. */
    expect(child.parentElement).toHaveStyle({ flexGrow: 1 })
    expect(child.parentElement?.getAttribute('style')).toContain('var(--pf-t--global--spacer--sm)')
    /* eslint-enable testing-library/no-node-access */
  })

  it('does not apply gutter by default', () => {
    const { container } = render(
      <SynPanelContentStack>
        <div>Item</div>
      </SynPanelContentStack>
    )
    /* eslint-disable testing-library/no-node-access -- Stack root has no accessible role; class checked via container. */
    expect(container.firstElementChild).not.toHaveClass('pf-m-gutter')
    /* eslint-enable testing-library/no-node-access */
  })

  it('applies gutter when hasGutter is passed', () => {
    const { container } = render(
      <SynPanelContentStack hasGutter>
        <div>Item</div>
      </SynPanelContentStack>
    )
    /* eslint-disable testing-library/no-node-access -- Stack root has no accessible role; class checked via container. */
    expect(container.firstElementChild).toHaveClass('pf-m-gutter')
    /* eslint-enable testing-library/no-node-access */
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with minimal content', async () => {
      const { container } = render(
        <SynPanelContentStack>
          <main>
            <h1>Title</h1>
          </main>
        </SynPanelContentStack>
      )
      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
