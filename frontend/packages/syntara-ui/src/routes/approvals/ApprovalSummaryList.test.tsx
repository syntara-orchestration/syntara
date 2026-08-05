import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'

import { ApprovalSummaryList } from './ApprovalSummaryList'

describe('ApprovalSummaryList', () => {
  const defaultProps = {
    workflowName: 'Production Deployment',
    approvalInitiatedAt: '2026-01-15T14:30:00Z',
  }

  it('renders approval type, workflow name, and initiated time', () => {
    render(<ApprovalSummaryList {...defaultProps} />)

    expect(screen.getByText('Approval type')).toBeInTheDocument()
    expect(screen.getByText('Approval step')).toBeInTheDocument()
    expect(screen.getByText('Workflow')).toBeInTheDocument()
    expect(screen.getByText('Production Deployment')).toBeInTheDocument()
    expect(screen.getByText('Approval initiated')).toBeInTheDocument()
    expect(screen.getByText(/Jan.*15.*2026/i)).toBeInTheDocument()
  })

  // The approvals API does not yet return workflow_id, so the link cannot be constructed.
  // Until that field is available the component renders the workflow name as plain text.
  it('renders workflow name as plain text when no workflow link is available', () => {
    render(<ApprovalSummaryList {...defaultProps} />)

    expect(screen.queryByRole('link', { name: 'Production Deployment' })).not.toBeInTheDocument()
    expect(screen.getByText('Production Deployment')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ApprovalSummaryList {...defaultProps} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
