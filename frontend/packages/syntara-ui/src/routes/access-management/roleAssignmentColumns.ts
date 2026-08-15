import type { FilterFieldDefinition } from '../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'

import type { RoleAssignmentRow } from './useRoleAssignmentData'

export type RoleAssignmentColumnKey = 'roleName' | 'description' | 'scope' | 'project'

export type ColumnDefinition = {
  key: RoleAssignmentColumnKey
  sortField: string
  sortRowKey: keyof RoleAssignmentRow
}

const allColumns: ColumnDefinition[] = [
  { key: 'roleName', sortField: 'role_name', sortRowKey: 'roleName' },
  { key: 'description', sortField: 'description', sortRowKey: 'roleDescription' },
  { key: 'scope', sortField: 'scope_type', sortRowKey: 'scopeType' },
  { key: 'project', sortField: 'project', sortRowKey: 'scope' },
]

export const filterKeyToColumn: Record<string, RoleAssignmentColumnKey> = {
  name: 'roleName',
  scope: 'scope',
  project: 'project',
}

export const allFilterFieldDefinitions: FilterFieldDefinition[] = [
  {
    key: 'name',
    label: 'Role name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by role name',
  },
  {
    key: 'scope',
    label: 'Scope',
    type: FilterTypeEnum.SELECT,
    options: [
      { value: 'system', label: 'System' },
      { value: 'project', label: 'Project' },
    ],
    placeholder: 'Filter by scope',
  },
  {
    key: 'project',
    label: 'Project',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by project',
  },
]

export function getVisibleColumns(hiddenColumns?: RoleAssignmentColumnKey[]): ColumnDefinition[] {
  if (!hiddenColumns?.length) return allColumns
  return allColumns.filter((col) => !hiddenColumns.includes(col.key))
}

export function buildSortMaps(visibleColumns: ColumnDefinition[]) {
  const sortFieldByColumn: Record<number, string> = {}
  const sortFieldToRowKey: Record<string, keyof RoleAssignmentRow> = {}
  for (let i = 0; i < visibleColumns.length; i++) {
    const col = visibleColumns[i]
    sortFieldByColumn[i] = col.sortField
    sortFieldToRowKey[col.sortField] = col.sortRowKey
  }
  return { sortFieldByColumn, sortFieldToRowKey }
}

export function sortRoleAssignmentRows(
  rows: RoleAssignmentRow[],
  activeSortIndex: number | undefined,
  sortDirection: 'asc' | 'desc',
  sortMaps: ReturnType<typeof buildSortMaps>
): RoleAssignmentRow[] {
  if (activeSortIndex === undefined) return rows
  const sortField = sortMaps.sortFieldByColumn[activeSortIndex]
  const rowKey = sortField ? sortMaps.sortFieldToRowKey[sortField] : undefined
  if (!rowKey) return rows

  return [...rows].sort((a, b) => {
    const rawA = a[rowKey]
    const rawB = b[rowKey]
    const aVal = typeof rawA === 'string' ? rawA : ''
    const bVal = typeof rawB === 'string' ? rawB : ''
    const cmp = aVal.localeCompare(bVal)
    return sortDirection === 'asc' ? cmp : -cmp
  })
}

export function applyRoleAssignmentFilters(rows: RoleAssignmentRow[], filters: { key: string; value: unknown }[]) {
  if (filters.length === 0) return rows
  return rows.filter((row) =>
    filters.every((filter) => {
      const value = typeof filter.value === 'string' ? filter.value : String(filter.value)
      switch (filter.key) {
        case 'name':
          return row.roleName.toLowerCase().includes(value.toLowerCase())
        case 'scope':
          return row.scopeType === value
        case 'project':
          return (row.scope ?? '').toLowerCase().includes(value.toLowerCase())
        default:
          return true
      }
    })
  )
}
