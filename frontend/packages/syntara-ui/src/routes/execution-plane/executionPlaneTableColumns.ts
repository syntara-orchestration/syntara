import type { SortableColumn, SortConfig } from '../../types/sorting'

/**
 * Column definitions for the Execution Plane targets table.
 * Node selectors live under placement and cannot be sorted via the API.
 */
export const executionPlaneTableColumns: SortableColumn[] = [
  { field: 'name', label: 'Name', isSortable: true },
  { field: 'cluster_id', label: 'OpenShift Cluster', isSortable: true },
  { field: 'status', label: 'Status', isSortable: true },
  { field: 'node_selectors', label: 'OpenShift node selector' },
  { field: 'enabled', label: 'State', isSortable: true },
]

/** Stable default sort — alphabetical by name (`sort=name`). */
export const executionPlaneDefaultSort: SortConfig = { field: 'name', direction: 'asc' }
