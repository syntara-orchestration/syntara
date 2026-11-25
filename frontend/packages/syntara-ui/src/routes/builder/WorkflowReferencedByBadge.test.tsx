import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useWorkflowUsedBy } from '../workflows/useWorkflowUsedBy'

import { WorkflowReferencedByBadge } from './WorkflowReferencedByBadge'

vi.mock('../workflows/useWorkflowUsedBy', () => ({
  useWorkflowUsedBy: vi.fn(),
}))

const mockedUseWorkflowUsedBy = vi.mocked(useWorkflowUsedBy)

function usedBy(overrides: Partial<ReturnType<typeof useWorkflowUsedBy>> = {}) {
  return {
    totalCount: 0,
    referencingParents: [],
    next: null,
    prev: null,
    isLoading: false,
    isError: false,
    ...overrides,
  }
}

describe('WorkflowReferencedByBadge', () => {
  it('renders nothing when the workflow has no published references', () => {
    mockedUseWorkflowUsedBy.mockReturnValue(usedBy({ totalCount: 0 }))
    const { container } = render(<WorkflowReferencedByBadge workflowId="wf-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the used-by count when the workflow is used as a sub-workflow', () => {
    mockedUseWorkflowUsedBy.mockReturnValue(usedBy({ totalCount: 2 }))
    render(<WorkflowReferencedByBadge workflowId="wf-1" />)
    expect(screen.getByText('Used by 2')).toBeInTheDocument()
  })

  it('shows an unavailable state when the lookup fails', () => {
    mockedUseWorkflowUsedBy.mockReturnValue(usedBy({ isError: true }))
    render(<WorkflowReferencedByBadge workflowId="wf-1" />)
    expect(screen.getByText('Used by: unavailable')).toBeInTheDocument()
  })

  it('renders nothing when no workflow id is provided', () => {
    mockedUseWorkflowUsedBy.mockReturnValue(usedBy())
    const { container } = render(<WorkflowReferencedByBadge workflowId={undefined} />)
    expect(container).toBeEmptyDOMElement()
  })
})
