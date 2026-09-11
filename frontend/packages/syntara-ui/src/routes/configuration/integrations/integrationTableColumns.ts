import type { SortableColumn, SortConfig } from '../../../types/sorting'

/**
 * Column definitions for the Integrations list table.
 * Non-sortable entries keep PatternFly `columnIndex` aligned with visible headers.
 * API URL and Enabled resources are derived values and cannot be sorted via the API.
 */
export const integrationTableColumns: SortableColumn[] = [
  { field: 'name', label: 'Server name / ID', isSortable: true },
  { field: 'validation_status', label: 'Status', isSortable: true },
  { field: 'integration_type', label: 'Integration type', isSortable: true },
  { field: 'api_url', label: 'API URL' },
  { field: 'enabled_resources', label: 'Enabled resources' },
  { field: 'last_validated_at', label: 'Last checked', isSortable: true },
  { field: 'enabled', label: 'State', isSortable: true },
]

/** Stable default sort — alphabetical by name (`sort=name`). */
export const integrationDefaultSort: SortConfig = { field: 'name', direction: 'asc' }
