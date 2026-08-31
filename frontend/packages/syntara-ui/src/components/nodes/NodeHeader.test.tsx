import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { NodeHeader } from './NodeHeader'

describe('NodeHeader', () => {
  it('renders children', () => {
    render(
      <NodeHeader>
        <span data-testid="child">Header Content</span>
      </NodeHeader>
    )

    expect(screen.getByTestId('child')).toBeInTheDocument()
    expect(screen.getByText('Header Content')).toBeInTheDocument()
  })

  it('renders multiple children', () => {
    render(
      <NodeHeader>
        <span data-testid="child-1">First</span>
        <span data-testid="child-2">Second</span>
        <span data-testid="child-3">Third</span>
      </NodeHeader>
    )

    expect(screen.getByTestId('child-1')).toBeInTheDocument()
    expect(screen.getByTestId('child-2')).toBeInTheDocument()
    expect(screen.getByTestId('child-3')).toBeInTheDocument()
  })

  it('applies padding styles', () => {
    render(
      <NodeHeader>
        <span>Content</span>
      </NodeHeader>
    )

    const headerDiv = screen.getByTestId('node-header')
    expect(headerDiv).toHaveStyle({
      paddingTop: 'var(--pf-t--global--spacer--md)',
      paddingLeft: 'var(--pf-t--global--spacer--md)',
      paddingRight: 'var(--pf-t--global--spacer--md)',
    })
  })

  it('uses Flex layout for children', () => {
    render(
      <NodeHeader>
        <span>Content</span>
      </NodeHeader>
    )

    const flexContainer = screen.getByTestId('node-header-content')
    expect(flexContainer).toBeInTheDocument()
  })

  it('renders without crashing with empty children', () => {
    render(<NodeHeader>{null}</NodeHeader>)
    expect(screen.getByTestId('node-header-content')).toBeInTheDocument()
  })

  it('renders complex nested content', () => {
    render(
      <NodeHeader>
        <div data-testid="icon-wrapper">
          <svg data-testid="icon" />
        </div>
        <div data-testid="title-wrapper">
          <h2>Title</h2>
          <span>Subtitle</span>
        </div>
        <button data-testid="menu-button">Menu</button>
      </NodeHeader>
    )

    expect(screen.getByTestId('icon-wrapper')).toBeInTheDocument()
    expect(screen.getByTestId('title-wrapper')).toBeInTheDocument()
    expect(screen.getByTestId('menu-button')).toBeInTheDocument()
  })
})
