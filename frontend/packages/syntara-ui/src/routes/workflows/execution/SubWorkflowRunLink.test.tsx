import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { MouseEvent, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { SubWorkflowRunLink } from './SubWorkflowRunLink'

// SynLink is a TanStack Router link that needs a router context; mock it to a
// plain button so this test exercises SubWorkflowRunLink in isolation without
// triggering jsdom navigation.
vi.mock('../../../components/SynLink', () => ({
  SynLink: ({
    children,
    onClick,
    to,
  }: Readonly<{ children: ReactNode; onClick?: (event: MouseEvent) => void; to: string }>) => (
    <button type="button" onClick={onClick} data-to={to} data-testid="syn-link">
      {children}
    </button>
  ),
}))

describe('SubWorkflowRunLink', () => {
  it('renders the child name suffix and targets the child execution', () => {
    render(<SubWorkflowRunLink childExecutionId="child-1" childName="My Child" />)

    const link = screen.getByTestId('syn-link')
    expect(link).toHaveTextContent('View sub-workflow run: My Child')
    expect(link).toHaveAttribute('data-to', '/executions/child-1')
  })

  it('omits the suffix when childName is null', () => {
    render(<SubWorkflowRunLink childExecutionId="child-2" childName={null} />)

    const link = screen.getByTestId('syn-link')
    expect(link).toHaveTextContent('View sub-workflow run')
    expect(link.textContent).not.toContain(':')
  })

  it('invokes the click handler (stopPropagation) without error', async () => {
    render(<SubWorkflowRunLink childExecutionId="child-3" childName="X" />)

    await userEvent.click(screen.getByTestId('syn-link'))

    expect(screen.getByTestId('syn-link')).toBeInTheDocument()
  })
})
