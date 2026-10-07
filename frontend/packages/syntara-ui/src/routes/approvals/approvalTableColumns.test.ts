import { describe, expect, it } from 'vitest'

import { approvalDefaultSort, approvalTableColumns, APPROVALS_TABLE_DATA_COLUMN_COUNT } from './approvalTableColumns'

describe('approvalTableColumns', () => {
  it('defines sortable name, created, decided, and status columns', () => {
    expect(approvalTableColumns).toEqual([
      { field: 'name', label: 'Approval name', isSortable: true },
      { field: 'created_at', label: 'Approval initiated', isSortable: true },
      { field: 'decided_at', label: 'Actioned on', isSortable: true },
      { field: 'status', label: 'Status', isSortable: true },
    ])
  })

  it('defaults to newest created_at first', () => {
    expect(approvalDefaultSort).toEqual({ field: 'created_at', direction: 'desc' })
  })

  it('exposes data column count for table layout', () => {
    expect(APPROVALS_TABLE_DATA_COLUMN_COUNT).toBe(5)
  })
})
