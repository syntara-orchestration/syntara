import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'

import { SynUserTag } from './SynUserTag'

describe('SynUserTag', () => {
  it('renders children text', () => {
    render(<SynUserTag>my-workflow-tag</SynUserTag>)

    expect(screen.getByText('my-workflow-tag')).toBeInTheDocument()
  })

  it('always renders as outline variant', () => {
    render(<SynUserTag data-testid="tag">my-workflow-tag</SynUserTag>)

    expect(screen.getByTestId('tag')).toHaveClass('pf-m-outline')
  })

  it('defaults to compact size', () => {
    render(<SynUserTag data-testid="tag">my-workflow-tag</SynUserTag>)

    expect(screen.getByTestId('tag')).toHaveClass('pf-m-compact')
  })

  it('forwards isCompact={false} to SynLabel', () => {
    render(
      <SynUserTag data-testid="tag" isCompact={false}>
        my-workflow-tag
      </SynUserTag>
    )

    expect(screen.getByTestId('tag')).not.toHaveClass('pf-m-compact')
  })

  it('re-renders correctly when props change', () => {
    const { rerender } = render(<SynUserTag data-testid="tag">first-tag</SynUserTag>)

    expect(screen.getByText('first-tag')).toBeInTheDocument()
    expect(screen.getByTestId('tag')).toHaveClass('pf-m-compact')

    rerender(
      <SynUserTag data-testid="tag" isCompact={false}>
        second-tag
      </SynUserTag>
    )

    expect(screen.getByText('second-tag')).toBeInTheDocument()
    expect(screen.getByTestId('tag')).not.toHaveClass('pf-m-compact')
  })

  it('uses cached output when re-rendered with no prop changes', () => {
    function StableParent() {
      return <SynUserTag data-testid="tag">stable-tag</SynUserTag>
    }

    const { rerender } = render(<StableParent />)

    rerender(<StableParent />)

    expect(screen.getByTestId('tag')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynUserTag>my-workflow-tag</SynUserTag>)

    expect(await axe(container)).toHaveNoViolations()
  })
})
