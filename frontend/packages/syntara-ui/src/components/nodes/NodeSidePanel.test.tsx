import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { NodeSidePanel } from './NodeSidePanel'

describe('NodeSidePanel', () => {
  it('renders children', () => {
    render(
      <NodeSidePanel>
        <div data-testid="panel-content">Panel Content</div>
      </NodeSidePanel>
    )

    expect(screen.getByTestId('panel-content')).toBeInTheDocument()
    expect(screen.getByText('Panel Content')).toBeInTheDocument()
  })

  it('renders multiple children in stack layout', () => {
    render(
      <NodeSidePanel>
        <div data-testid="section-1">Section 1</div>
        <div data-testid="section-2">Section 2</div>
        <div data-testid="section-3">Section 3</div>
      </NodeSidePanel>
    )

    expect(screen.getByTestId('section-1')).toBeInTheDocument()
    expect(screen.getByTestId('section-2')).toBeInTheDocument()
    expect(screen.getByTestId('section-3')).toBeInTheDocument()
  })

  it('applies padding styles', () => {
    render(
      <NodeSidePanel>
        <div>Content</div>
      </NodeSidePanel>
    )

    const stack = screen.getByTestId('node-side-panel')
    expect(stack).toBeInTheDocument()
    expect(stack.getAttribute('style')).toContain('padding: var(--pf-t--global--spacer--2xl)')
  })

  it('has gutter between stacked items', () => {
    render(
      <NodeSidePanel>
        <div>Item 1</div>
        <div>Item 2</div>
      </NodeSidePanel>
    )

    const stack = screen.getByTestId('node-side-panel')
    expect(stack).toHaveClass('pf-m-gutter')
  })

  it('renders without crashing with empty children', () => {
    render(<NodeSidePanel>{null}</NodeSidePanel>)
    expect(screen.getByTestId('node-side-panel')).toBeInTheDocument()
  })

  it('renders form elements as children', () => {
    render(
      <NodeSidePanel>
        <form data-testid="form">
          <label htmlFor="name">Name</label>
          <input id="name" type="text" />
          <button type="submit">Submit</button>
        </form>
      </NodeSidePanel>
    )

    expect(screen.getByTestId('form')).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Submit' })).toBeInTheDocument()
  })

  it('renders details sections as children', () => {
    render(
      <NodeSidePanel>
        <section data-testid="details">
          <h3>Details</h3>
          <dl>
            <dt>Status</dt>
            <dd>Running</dd>
          </dl>
        </section>
      </NodeSidePanel>
    )

    expect(screen.getByTestId('details')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
    expect(screen.getByText('Running')).toBeInTheDocument()
  })
})
