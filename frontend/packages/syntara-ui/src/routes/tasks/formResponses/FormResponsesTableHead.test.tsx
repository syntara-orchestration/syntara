import { Table } from '@patternfly/react-table'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormResponsesTableHead } from './FormResponsesTableHead'

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

describe('FormResponsesTableHead', () => {
  it('renders sortable column headers and wires expand-all', async () => {
    const getSortParams = vi.fn(getSortParamsStub)
    const onCollapseAll = vi.fn()
    const user = userEvent.setup()

    render(
      <Table aria-label="Form responses" isExpandable>
        <FormResponsesTableHead
          getSortParams={getSortParams}
          allRowsExpanded={false}
          collapseAllAriaLabel="Expand all"
          onCollapseAll={onCollapseAll}
        />
      </Table>
    )

    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Workflow' })).toBeInTheDocument()
    expect(getSortParams).toHaveBeenCalledWith('name')
    expect(getSortParams).toHaveBeenCalledWith('workflow_name')
    expect(getSortParams).toHaveBeenCalledWith('responded_at')
    expect(getSortParams).toHaveBeenCalledWith('created_at')
    expect(getSortParams).toHaveBeenCalledWith('status')

    await user.click(screen.getByRole('button', { name: /expand all/i }))
    expect(onCollapseAll).toHaveBeenCalled()
  })

  it('wires expand-all when parent reports every row expanded', async () => {
    const user = userEvent.setup()
    const onCollapseAll = vi.fn()

    render(
      <Table aria-label="Form responses" isExpandable>
        <FormResponsesTableHead
          getSortParams={getSortParamsStub}
          allRowsExpanded={true}
          collapseAllAriaLabel="Collapse all"
          onCollapseAll={onCollapseAll}
        />
      </Table>
    )

    // PatternFly uses areAllExpanded: !allRowsExpanded, so the control label stays "Expand all".
    await user.click(screen.getByRole('button', { name: /expand all/i }))
    expect(onCollapseAll).toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Table aria-label="Form responses" isExpandable>
        <FormResponsesTableHead
          getSortParams={getSortParamsStub}
          allRowsExpanded={true}
          collapseAllAriaLabel="Collapse all"
          onCollapseAll={vi.fn()}
        />
      </Table>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
