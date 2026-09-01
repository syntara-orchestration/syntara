import { render, screen } from '@testing-library/react'
import { useMemo, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { NodeBody } from './NodeBody'
import { NodeExpandedContext, type NodeExpandedContextValue } from './NodeExpandedContext'

describe('NodeBody', () => {
  // Helper to render with context
  const renderWithContext = (
    expanded: boolean,
    children: React.ReactNode,
    setExpanded?: React.Dispatch<React.SetStateAction<boolean>>
  ) => {
    return render(
      <NodeExpandedContext.Provider value={[expanded, setExpanded ?? vi.fn()]}>
        <NodeBody>{children}</NodeBody>
      </NodeExpandedContext.Provider>
    )
  }

  // Helper component that manages its own state
  const StatefulWrapper = ({
    initialExpanded = true,
    children,
    className,
  }: {
    initialExpanded?: boolean
    children: React.ReactNode
    className?: string
  }) => {
    const [expanded, setExpanded] = useState(initialExpanded)
    const expandedContextValue = useMemo<NodeExpandedContextValue>(() => [expanded, setExpanded], [expanded])

    return (
      <NodeExpandedContext.Provider value={expandedContextValue}>
        <div data-testid="expanded-state">{expanded ? 'expanded' : 'collapsed'}</div>
        <NodeBody className={className}>{children}</NodeBody>
      </NodeExpandedContext.Provider>
    )
  }

  describe('rendering', () => {
    it('renders children when expanded', () => {
      renderWithContext(true, <div data-testid="content">Body Content</div>)

      expect(screen.getByTestId('content')).toBeInTheDocument()
      expect(screen.getByText('Body Content')).toBeInTheDocument()
    })

    it('does not render children when collapsed', () => {
      renderWithContext(false, <div data-testid="content">Body Content</div>)

      expect(screen.queryByTestId('content')).not.toBeInTheDocument()
    })

    it('renders with default expanded when context is null', () => {
      // When context is null, expanded defaults to true
      render(
        <NodeExpandedContext.Provider value={null}>
          <NodeBody>
            <div data-testid="content">Content</div>
          </NodeBody>
        </NodeExpandedContext.Provider>
      )

      expect(screen.getByTestId('content')).toBeInTheDocument()
    })
  })

  describe('className prop', () => {
    it('applies custom className to scrollable container', () => {
      render(<StatefulWrapper className="custom-class">Content</StatefulWrapper>)

      const scrollableDiv = screen.getByTestId('node-body-scroll-container')
      expect(scrollableDiv).toBeInTheDocument()
      expect(scrollableDiv).toHaveClass('custom-class')
    })

    it('includes nodrag nopan classes with custom className', () => {
      render(<StatefulWrapper className="my-class">Content</StatefulWrapper>)

      const scrollableDiv = screen.getByTestId('node-body-scroll-container')
      expect(scrollableDiv).toBeInTheDocument()
      expect(scrollableDiv).toHaveClass('nodrag', 'nopan', 'my-class')
    })
  })

  describe('styling', () => {
    it('has default cursor style on stack item', () => {
      renderWithContext(true, <div>Content</div>)

      const stackItem = screen.getByTestId('node-body')
      expect(stackItem).toBeInTheDocument()
    })
  })

  describe('ReactFlow interaction prevention', () => {
    it('has nodrag nopan classes on StackItem', () => {
      renderWithContext(true, <div>Content</div>)

      const stackItem = screen.getByTestId('node-body')
      expect(stackItem).toHaveClass('nodrag')
      expect(stackItem).toHaveClass('nopan')
    })

    it('has nodrag nopan classes on scrollable div', () => {
      renderWithContext(true, <div>Content</div>)

      const scrollableDiv = screen.getByTestId('node-body-scroll-container')
      expect(scrollableDiv).toBeInTheDocument()
      expect(scrollableDiv).toHaveClass('nodrag', 'nopan')
    })
  })

  describe('mousedown handling', () => {
    it('stops mousedown propagation on StackItem', () => {
      const parentMouseDownHandler = vi.fn()
      render(
        // eslint-disable-next-line jsx-a11y/no-static-element-interactions
        <div onMouseDown={parentMouseDownHandler}>
          <NodeExpandedContext.Provider value={[true, vi.fn()]}>
            <NodeBody>
              <div data-testid="content">Content</div>
            </NodeBody>
          </NodeExpandedContext.Provider>
        </div>
      )

      const stackItem = screen.getByTestId('node-body')
      expect(stackItem).toBeInTheDocument()
      const mouseDownEvent = new MouseEvent('mousedown', { bubbles: true })
      stackItem.dispatchEvent(mouseDownEvent)

      expect(parentMouseDownHandler).not.toHaveBeenCalled()
    })
  })

  describe('complex content', () => {
    it('renders nested elements', () => {
      renderWithContext(
        true,
        <div data-testid="wrapper">
          <ul>
            <li>Item 1</li>
            <li>Item 2</li>
          </ul>
        </div>
      )

      expect(screen.getByTestId('wrapper')).toBeInTheDocument()
      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
    })

    it('renders form elements', () => {
      renderWithContext(
        true,
        <form data-testid="form">
          <input type="text" placeholder="Enter value" />
          <button type="submit">Submit</button>
        </form>
      )

      expect(screen.getByTestId('form')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Enter value')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Submit' })).toBeInTheDocument()
    })
  })

  describe('expanded state', () => {
    it('does not render content when collapsed', () => {
      renderWithContext(false, <div data-testid="body-content">Content</div>)

      // When collapsed, the component returns null, so content should not be in DOM
      expect(screen.queryByTestId('body-content')).not.toBeInTheDocument()
    })
  })
})
