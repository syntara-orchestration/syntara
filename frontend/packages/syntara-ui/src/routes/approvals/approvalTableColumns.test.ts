import { describe, expect, it } from 'vitest'

import { approvalDefaultSort, approvalTableColumns } from './approvalTableColumns'

describe('approvalTableColumns', () => {
  it('defines sortable name, workflow, created, decided, and status columns', () => {
    expect(approvalTableColumns).toEqual([
      { field: 'name', label: 'Approval name', isSortable: true },
      { field: 'workflow_name', label: 'Workflow', isSortable: true },
      { field: 'created_at', label: 'Approval initiated', isSortable: true },
      { field: 'decided_at', label: 'Actioned on', isSortable: true },
      { field: 'status', label: 'Status', isSortable: true },
    ])
  })

  it('defaults to newest created_at first', () => {
    expect(approvalDefaultSort).toEqual({ field: 'created_at', direction: 'desc' })
  })
})
