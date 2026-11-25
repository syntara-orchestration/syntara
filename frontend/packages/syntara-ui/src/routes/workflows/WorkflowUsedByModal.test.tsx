import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useWorkflowUsedBy } from './useWorkflowUsedBy'
import { WorkflowUsedByModal } from './WorkflowUsedByModal'

vi.mock('./useWorkflowUsedBy', () => ({ useWorkflowUsedBy: vi.fn() }))
vi.mock('../../components/SynLink', () => ({
  SynLink: ({ to, children }: { to: string; children: ReactNode }) => <a href={to}>{children}</a>,
}))

const mockedUseWorkflowUsedBy = vi.mocked(useWorkflowUsedBy)

function usedBy(overrides: Partial<ReturnType<typeof useWorkflowUsedBy>> = {}): ReturnType<typeof useWorkflowUsedBy> {
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

describe('WorkflowUsedByModal', () => {
  it('lists the referencing parents with links and shows the total', () => {
    mockedUseWorkflowUsedBy.mockReturnValue(
      usedBy({
        totalCount: 2,
        referencingParents: [
          { id: 'p1', name: 'Parent One' },
          { id: 'p2', name: 'Parent Two' },
        ] as never,
      })
    )

    render(<WorkflowUsedByModal isOpen onClose={vi.fn()} workflowId="wf-1" />)

    expect(screen.getByText(/2 published workflows use this workflow/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Parent One' })).toHaveAttribute('href', '/workflow-builder/p1')
    expect(screen.getByRole('link', { name: 'Parent Two' })).toBeInTheDocument()
    // compact page size requested from the backend (cursor pagination, not client-side slicing)
    expect(mockedUseWorkflowUsedBy).toHaveBeenCalledWith('wf-1', expect.objectContaining({ limit: 10 }))
    expect(screen.getByText('Only workflows you have permission to view are listed.')).toBeInTheDocument()
  })

  it('enables Next only when another page exists', () => {
    mockedUseWorkflowUsedBy.mockReturnValue(
      usedBy({ totalCount: 30, referencingParents: [{ id: 'p1', name: 'P1' }] as never, next: 'cursor-2' })
    )

    render(<WorkflowUsedByModal isOpen onClose={vi.fn()} workflowId="wf-1" />)

    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  })

  it('shows an error message when the lookup fails', () => {
    mockedUseWorkflowUsedBy.mockReturnValue(usedBy({ isError: true }))

    render(<WorkflowUsedByModal isOpen onClose={vi.fn()} workflowId="wf-1" />)

    expect(screen.getByText(/Unable to load the list of workflows/)).toBeInTheDocument()
  })

  it('does not show a zero count while loading', () => {
    mockedUseWorkflowUsedBy.mockReturnValue(usedBy({ isLoading: true }))

    render(<WorkflowUsedByModal isOpen onClose={vi.fn()} workflowId="wf-1" />)

    expect(screen.queryByText(/use this workflow as a sub-workflow/)).not.toBeInTheDocument()
  })
})
