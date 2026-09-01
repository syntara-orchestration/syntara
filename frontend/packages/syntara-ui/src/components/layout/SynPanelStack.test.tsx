import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynPanelStack, SynPanelStackItem } from './SynPanelStack'

describe('SynPanelStack', () => {
  it('keeps overflow visible on the stack so panel box-shadow is not clipped', () => {
    render(
      <SynPanelStack data-testid="panel-stack">
        <SynPanelStackItem>
          <div>Pane</div>
        </SynPanelStackItem>
      </SynPanelStack>
    )

    expect(screen.getByTestId('panel-stack')).toHaveStyle({ overflow: 'visible' })
  })

  it('keeps overflow visible even when a caller passes overflow hidden', () => {
    render(
      <SynPanelStack data-testid="panel-stack" style={{ overflow: 'hidden' }}>
        <SynPanelStackItem data-testid="panel-slot" style={{ overflow: 'hidden' }}>
          <div>Pane</div>
        </SynPanelStackItem>
      </SynPanelStack>
    )

    expect(screen.getByTestId('panel-stack')).toHaveStyle({ overflow: 'visible' })
    expect(screen.getByTestId('panel-slot')).toHaveStyle({ overflow: 'visible' })
  })

  it('marks filled items as PatternFly fill slots', () => {
    render(
      <SynPanelStack>
        <SynPanelStackItem isFilled data-testid="filled-slot">
          <div>Canvas</div>
        </SynPanelStackItem>
        <SynPanelStackItem data-testid="fixed-slot" style={{ height: '120px' }}>
          <div>Details</div>
        </SynPanelStackItem>
      </SynPanelStack>
    )

    expect(screen.getByTestId('filled-slot')).toHaveClass('pf-m-fill')
    expect(screen.getByTestId('fixed-slot')).not.toHaveClass('pf-m-fill')
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with stacked panes', async () => {
      const { container } = render(
        <SynPanelStack>
          <SynPanelStackItem isFilled>
            <main>
              <h1>Canvas</h1>
            </main>
          </SynPanelStackItem>
          <SynPanelStackItem>
            <section>
              <h2>Details</h2>
            </section>
          </SynPanelStackItem>
        </SynPanelStack>
      )
      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
