import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useMemo, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { NodeExpandedContext, type NodeExpandedContextValue } from './NodeExpandedContext'
import { NodeExpandToggle } from './NodeExpandToggle'

describe('NodeExpandToggle', () => {
  // Helper to render with context
  const renderWithContext = (expanded: boolean, setExpanded: React.Dispatch<React.SetStateAction<boolean>>) => {
    return render(
      <NodeExpandedContext.Provider value={[expanded, setExpanded]}>
        <NodeExpandToggle />
      </NodeExpandedContext.Provider>
    )
  }

  // Helper component that manages its own state
  const StatefulWrapper = ({ initialExpanded = true }: { initialExpanded?: boolean }) => {
    const [expanded, setExpanded] = useState(initialExpanded)
    const expandedContextValue = useMemo<NodeExpandedContextValue>(() => [expanded, setExpanded], [expanded])

    return (
      <NodeExpandedContext.Provider value={expandedContextValue}>
        <div data-testid="expanded-state">{expanded ? 'expanded' : 'collapsed'}</div>
        <NodeExpandToggle />
      </NodeExpandedContext.Provider>
    )
  }

  describe('rendering', () => {
    it('returns null when context is not provided', () => {
      const { container } = render(<NodeExpandToggle />)
      expect(container).toBeEmptyDOMElement()
    })

    it('renders toggle when context is provided', () => {
      const setExpanded = vi.fn()
      renderWithContext(true, setExpanded)

      expect(screen.getByTestId('node-expand-toggle')).toBeInTheDocument()
    })

    it('renders with expanded rotation (180deg) when expanded', () => {
      const setExpanded = vi.fn()
      renderWithContext(true, setExpanded)

      const iconWrapper = screen.getByTestId('node-expand-toggle')
      expect(iconWrapper).toHaveStyle({ transform: 'rotate(180deg)' })
    })

    it('renders with collapsed rotation (0deg) when collapsed', () => {
      const setExpanded = vi.fn()
      renderWithContext(false, setExpanded)

      const iconWrapper = screen.getByTestId('node-expand-toggle')
      expect(iconWrapper).toHaveStyle({ transform: 'rotate(0deg)' })
    })
  })

  describe('click interaction', () => {
    it('toggles expanded state from true to false on click', async () => {
      const user = userEvent.setup()
      render(<StatefulWrapper initialExpanded={true} />)

      expect(screen.getByTestId('expanded-state')).toHaveTextContent('expanded')

      await user.click(screen.getByTestId('node-expand-toggle'))

      expect(screen.getByTestId('expanded-state')).toHaveTextContent('collapsed')
    })

    it('toggles expanded state from false to true on click', async () => {
      const user = userEvent.setup()
      render(<StatefulWrapper initialExpanded={false} />)

      expect(screen.getByTestId('expanded-state')).toHaveTextContent('collapsed')

      await user.click(screen.getByTestId('node-expand-toggle'))

      expect(screen.getByTestId('expanded-state')).toHaveTextContent('expanded')
    })

    it('stops event propagation on click', async () => {
      const user = userEvent.setup()
      const parentClickHandler = vi.fn()

      render(
        // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
        <div onClick={parentClickHandler}>
          <StatefulWrapper />
        </div>
      )

      await user.click(screen.getByTestId('node-expand-toggle'))

      expect(parentClickHandler).not.toHaveBeenCalled()
    })
  })

  describe('mouse interaction', () => {
    it('stops mousedown propagation', async () => {
      const user = userEvent.setup()
      const parentMouseDownHandler = vi.fn()

      render(
        // eslint-disable-next-line jsx-a11y/no-static-element-interactions
        <div onMouseDown={parentMouseDownHandler}>
          <StatefulWrapper />
        </div>
      )

      // userEvent.click triggers mousedown, so parent should not receive it
      await user.click(screen.getByTestId('node-expand-toggle'))

      expect(parentMouseDownHandler).not.toHaveBeenCalled()
    })
  })

  describe('keyboard interaction', () => {
    it('stops Enter key propagation', async () => {
      const user = userEvent.setup()
      const parentKeyDownHandler = vi.fn()

      render(
        // eslint-disable-next-line jsx-a11y/no-static-element-interactions
        <div onKeyDown={parentKeyDownHandler}>
          <StatefulWrapper />
        </div>
      )

      const icon = screen.getByTestId('node-expand-toggle')
      icon.focus()
      expect(icon).toHaveFocus()
      await user.keyboard('{Enter}')

      expect(parentKeyDownHandler).not.toHaveBeenCalled()
    })

    it('stops Space key propagation', async () => {
      const user = userEvent.setup()
      const parentKeyDownHandler = vi.fn()

      render(
        // eslint-disable-next-line jsx-a11y/no-static-element-interactions
        <div onKeyDown={parentKeyDownHandler}>
          <StatefulWrapper />
        </div>
      )

      const icon = screen.getByTestId('node-expand-toggle')
      icon.focus()
      expect(icon).toHaveFocus()
      await user.keyboard(' ')

      expect(parentKeyDownHandler).not.toHaveBeenCalled()
    })
  })

  describe('styling', () => {
    it('has nodrag nopan class to prevent ReactFlow interactions', () => {
      const setExpanded = vi.fn()
      renderWithContext(true, setExpanded)

      const iconWrapper = screen.getByTestId('node-expand-toggle')
      expect(iconWrapper).toHaveClass('nodrag')
      expect(iconWrapper).toHaveClass('nopan')
    })

    it('is focusable as a button for keyboard interaction', () => {
      const setExpanded = vi.fn()
      renderWithContext(true, setExpanded)

      const iconWrapper = screen.getByTestId('node-expand-toggle')
      expect(iconWrapper).toHaveAttribute('role', 'button')
      expect(iconWrapper).toHaveAttribute('tabIndex', '0')
    })

    it('has pointer cursor style', () => {
      const setExpanded = vi.fn()
      renderWithContext(true, setExpanded)

      const iconWrapper = screen.getByTestId('node-expand-toggle')
      expect(iconWrapper).toHaveStyle({ cursor: 'pointer' })
    })

    it('has transition for smooth rotation', () => {
      const setExpanded = vi.fn()
      renderWithContext(true, setExpanded)

      const iconWrapper = screen.getByTestId('node-expand-toggle')
      expect(iconWrapper).toHaveStyle({ transition: 'transform 0.2s ease-out' })
    })
  })
})
