import { describe, expect, it } from 'vitest'

import {
  applyRoleAssignmentFilters,
  buildSortMaps,
  getVisibleColumns,
  sortRoleAssignmentRows,
} from './roleAssignmentColumns'
import type { RoleAssignmentRow } from './useRoleAssignmentData'

const makeRow = (overrides: Partial<RoleAssignmentRow> = {}): RoleAssignmentRow => ({
  id: 'a1',
  roleName: 'Admin',
  roleDescription: 'Full access',
  policies: [{ name: 'policy-a' }],
  scope: 'System',
  scopeType: 'system',
  createdAt: null,
  ...overrides,
})

const rows: RoleAssignmentRow[] = [
  makeRow({ id: 'a1', roleName: 'Admin', scopeType: 'system', scope: 'System' }),
  makeRow({ id: 'a2', roleName: 'Viewer', scopeType: 'project', scope: 'Project Alpha' }),
  makeRow({ id: 'a3', roleName: 'Editor', scopeType: 'project', scope: 'Project Beta' }),
]

describe('applyRoleAssignmentFilters', () => {
  it('returns all rows when no filters are provided', () => {
    expect(applyRoleAssignmentFilters(rows, [])).toBe(rows)
  })

  describe('name filter', () => {
    it('filters by role name (case-insensitive)', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'name', value: 'admin' }])
      expect(result).toHaveLength(1)
      expect(result[0].roleName).toBe('Admin')
    })

    it('matches partial role names', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'name', value: 'iew' }])
      expect(result).toHaveLength(1)
      expect(result[0].roleName).toBe('Viewer')
    })

    it('returns empty when no role names match', () => {
      expect(applyRoleAssignmentFilters(rows, [{ key: 'name', value: 'nonexistent' }])).toHaveLength(0)
    })
  })

  describe('scope filter', () => {
    it('filters by system scope', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'scope', value: 'system' }])
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('a1')
    })

    it('filters by project scope', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'scope', value: 'project' }])
      expect(result).toHaveLength(2)
    })

    it('returns empty for non-matching scope', () => {
      expect(applyRoleAssignmentFilters(rows, [{ key: 'scope', value: 'other' }])).toHaveLength(0)
    })
  })

  describe('project filter', () => {
    it('filters by project name (case-insensitive)', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'project', value: 'alpha' }])
      expect(result).toHaveLength(1)
      expect(result[0].scope).toBe('Project Alpha')
    })

    it('matches partial project names', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'project', value: 'project' }])
      expect(result).toHaveLength(2)
    })

    it('matches system rows with "System" scope text', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'project', value: 'system' }])
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('a1')
    })
  })

  describe('multiple filters', () => {
    it('applies all filters (AND logic)', () => {
      const result = applyRoleAssignmentFilters(rows, [
        { key: 'scope', value: 'project' },
        { key: 'name', value: 'viewer' },
      ])
      expect(result).toHaveLength(1)
      expect(result[0].roleName).toBe('Viewer')
    })

    it('returns empty when filters contradict', () => {
      const result = applyRoleAssignmentFilters(rows, [
        { key: 'scope', value: 'system' },
        { key: 'project', value: 'alpha' },
      ])
      expect(result).toHaveLength(0)
    })
  })

  describe('unknown filter key', () => {
    it('ignores unknown filter keys (always passes)', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'unknown_key', value: 'anything' }])
      expect(result).toHaveLength(3)
    })
  })

  describe('non-string filter value', () => {
    it('coerces non-string values via String()', () => {
      const result = applyRoleAssignmentFilters(rows, [{ key: 'name', value: 123 }])
      expect(result).toHaveLength(0)
    })
  })

  describe('nullish scope', () => {
    it('handles row with undefined scope in project filter', () => {
      const rowsWithNullScope = [makeRow({ id: 'x1', scope: undefined as unknown as string })]
      const result = applyRoleAssignmentFilters(rowsWithNullScope, [{ key: 'project', value: 'anything' }])
      expect(result).toHaveLength(0)
    })
  })
})

describe('sortRoleAssignmentRows', () => {
  const visibleColumns = getVisibleColumns()
  const sortMaps = buildSortMaps(visibleColumns)

  it('returns rows unchanged when activeSortIndex is undefined', () => {
    expect(sortRoleAssignmentRows(rows, undefined, 'asc', sortMaps)).toBe(rows)
  })

  it('sorts by roleName ascending', () => {
    const roleNameIndex = visibleColumns.findIndex((c) => c.key === 'roleName')
    const sorted = sortRoleAssignmentRows(rows, roleNameIndex, 'asc', sortMaps)
    expect(sorted.map((r) => r.roleName)).toEqual(['Admin', 'Editor', 'Viewer'])
  })

  it('sorts by roleName descending', () => {
    const roleNameIndex = visibleColumns.findIndex((c) => c.key === 'roleName')
    const sorted = sortRoleAssignmentRows(rows, roleNameIndex, 'desc', sortMaps)
    expect(sorted.map((r) => r.roleName)).toEqual(['Viewer', 'Editor', 'Admin'])
  })

  it('does not mutate the original array', () => {
    const roleNameIndex = visibleColumns.findIndex((c) => c.key === 'roleName')
    const original = [...rows]
    sortRoleAssignmentRows(rows, roleNameIndex, 'desc', sortMaps)
    expect(rows).toEqual(original)
  })

  it('returns rows unchanged for an out-of-range sort index', () => {
    const sorted = sortRoleAssignmentRows(rows, 99, 'asc', sortMaps)
    expect(sorted).toBe(rows)
  })

  it('treats non-string sort values as empty string', () => {
    const rowsWithNull = [
      makeRow({ id: 'n1', roleName: 'B', roleDescription: null }),
      makeRow({ id: 'n2', roleName: 'A', roleDescription: 'Has description' }),
    ]
    const descIndex = visibleColumns.findIndex((c) => c.key === 'description')
    const sorted = sortRoleAssignmentRows(rowsWithNull, descIndex, 'asc', sortMaps)
    // null coerces to '' which sorts before 'Has description'
    expect(sorted.map((r) => r.id)).toEqual(['n1', 'n2'])
  })
})

describe('getVisibleColumns', () => {
  it('returns all columns when no hidden columns specified', () => {
    const cols = getVisibleColumns()
    expect(cols.map((c) => c.key)).toEqual(['roleName', 'description', 'scope', 'project'])
  })

  it('returns all columns for empty array', () => {
    expect(getVisibleColumns([])).toEqual(getVisibleColumns())
  })

  it('hides specified columns', () => {
    const cols = getVisibleColumns(['scope', 'project'])
    expect(cols.map((c) => c.key)).toEqual(['roleName', 'description'])
  })
})

describe('buildSortMaps', () => {
  it('maps column indices to sort fields', () => {
    const cols = getVisibleColumns(['scope'])
    const maps = buildSortMaps(cols)
    expect(maps.sortFieldByColumn[0]).toBe('role_name')
    expect(maps.sortFieldByColumn[1]).toBe('description')
    expect(maps.sortFieldByColumn[2]).toBe('project')
  })

  it('maps sort fields to row keys', () => {
    const cols = getVisibleColumns()
    const maps = buildSortMaps(cols)
    expect(maps.sortFieldToRowKey['role_name']).toBe('roleName')
    expect(maps.sortFieldToRowKey['description']).toBe('roleDescription')
  })
})
