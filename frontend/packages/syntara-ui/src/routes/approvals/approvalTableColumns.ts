import type { SortableColumn, SortConfig } from '../../types/sorting'

/** Sortable column definitions for the Approvals list table. */
export const approvalTableColumns: SortableColumn[] = [
  { field: 'name', label: 'Approval name', isSortable: true },
  { field: 'created_at', label: 'Approval initiated', isSortable: true },
  { field: 'decided_at', label: 'Actioned on', isSortable: true },
  { field: 'status', label: 'Status', isSortable: true },
]

/** Stable default sort — newest requested first (`sort=-created_at`). */
export const approvalDefaultSort: SortConfig = { field: 'created_at', direction: 'desc' }

/** Visible data columns in the approvals list (excluding select and expand controls). */
export const APPROVALS_TABLE_DATA_COLUMN_COUNT = 5
