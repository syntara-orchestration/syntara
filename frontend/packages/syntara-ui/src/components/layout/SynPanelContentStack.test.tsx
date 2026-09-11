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
    // Assert on the literal inline style rather than toHaveStyle()/getComputedStyle: happy-dom
    // serializes a zero-length computed min-height as "0" (no unit), so a computed-style
    // comparison is unreliable here.
    const stackStyle = child.parentElement?.style
    expect(stackStyle?.height).toBe('100%')
    expect(stackStyle?.flexGrow).toBe('1')
    expect(stackStyle?.minHeight).toBe('0')
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
