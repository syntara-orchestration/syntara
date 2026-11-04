import type { SortableColumn, SortConfig } from '../../../types/sorting'

/** Sortable column definitions for the Form responses list table. */
export const formResponseTableColumns: SortableColumn[] = [
  { field: 'name', label: 'Name', isSortable: true },
  { field: 'workflow_name', label: 'Workflow', isSortable: true },
  { field: 'created_at', label: 'Initiated', isSortable: true },
  { field: 'responded_at', label: 'Actioned on', isSortable: true },
  { field: 'status', label: 'Status', isSortable: true },
]

/** Stable default sort — newest prompts first (`sort=-created_at`). */
export const formResponseDefaultSort: SortConfig = { field: 'created_at', direction: 'desc' }

/** Visible data columns in the form responses list (excluding the expand control column). */
export const FORM_RESPONSES_TABLE_DATA_COLUMN_COUNT = 5
