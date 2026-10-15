import { Table } from '@patternfly/react-table'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ApprovalsTableHead } from './ApprovalsTableHead'

function getSortParamsStub(columnField: string) {
  return {
    sortBy: {
      index: 0,
      direction: 'asc' as const,
      defaultDirection: 'asc' as const,
    },
    onSort: vi.fn(),
    columnIndex: 0,
    'aria-label': columnField,
  }
}

describe('ApprovalsTableHead', () => {
  it('has no accessibility violations', async () => {
    const getSortParams = vi.fn(getSortParamsStub)

    const { container } = render(
      <Table aria-label="Approvals" isExpandable>
        <ApprovalsTableHead
          getSortParams={getSortParams}
          allRowsExpanded={false}
          collapseAllAriaLabel="Collapse all rows"
          onCollapseAll={vi.fn()}
        />
      </Table>
    )

    expect(await axe(container)).toHaveNoViolations()
    expect(getSortParams).toHaveBeenCalledWith('name')
    expect(getSortParams).toHaveBeenCalledWith('workflow_name')
    expect(getSortParams).toHaveBeenCalledWith('created_at')
    expect(getSortParams).toHaveBeenCalledWith('decided_at')
    expect(getSortParams).toHaveBeenCalledWith('status')
  })

  it('renders the expand-all toggle when hasExpandableRows is true (default)', () => {
    render(
      <Table aria-label="Approvals" isExpandable>
        <ApprovalsTableHead
          getSortParams={getSortParamsStub}
          allRowsExpanded={false}
          collapseAllAriaLabel="Expand all"
          onCollapseAll={vi.fn()}
        />
      </Table>
    )

    expect(screen.getByRole('button', { name: /expand all/i })).toBeInTheDocument()
  })

  it('hides the expand-all toggle when hasExpandableRows is false', () => {
    render(
      <Table aria-label="Approvals" isExpandable>
        <ApprovalsTableHead
          getSortParams={getSortParamsStub}
          allRowsExpanded={false}
          collapseAllAriaLabel="Expand all"
          onCollapseAll={vi.fn()}
          hasExpandableRows={false}
        />
      </Table>
    )

    expect(screen.queryByRole('button', { name: /expand all/i })).not.toBeInTheDocument()
  })

  it('has no accessibility violations when the expand-all toggle is hidden', async () => {
    const { container } = render(
      <Table aria-label="Approvals" isExpandable>
        <ApprovalsTableHead
          getSortParams={getSortParamsStub}
          allRowsExpanded={false}
          collapseAllAriaLabel="Expand all"
          onCollapseAll={vi.fn()}
          hasExpandableRows={false}
        />
      </Table>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
