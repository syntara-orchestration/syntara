import { describe, expect, it } from 'vitest'

import type { FilterConfig } from '../../types/filters'

import { buildPermissionRow, buildSortParam, derivePrincipalType, transformAssignmentFilters } from './assignmentUtils'
import type { RoleAssignmentRead } from './types'

describe('transformAssignmentFilters', () => {
  it('maps name key to principal_name', () => {
    const filters = [{ key: 'name', value: 'alice' }] as FilterConfig[]
    const result = transformAssignmentFilters(filters)
    expect(result[0].key).toBe('principal_name')
  })

  it('maps type key to principal_type', () => {
    const filters = [{ key: 'type', value: 'user' }] as FilterConfig[]
    const result = transformAssignmentFilters(filters)
    expect(result[0].key).toBe('principal_type')
  })

  it('maps project key to project_id', () => {
    const filters = [{ key: 'project', value: 'p1' }] as FilterConfig[]
    const result = transformAssignmentFilters(filters)
    expect(result[0].key).toBe('project_id')
  })

  it('passes through scope key unchanged', () => {
    const filters = [{ key: 'scope', value: 'system' }] as FilterConfig[]
    const result = transformAssignmentFilters(filters)
    expect(result[0].key).toBe('scope')
  })

  it('passes through unrecognized keys unchanged', () => {
    const filters = [{ key: 'role_name', value: 'Admin' }] as FilterConfig[]
    const result = transformAssignmentFilters(filters)
    expect(result[0].key).toBe('role_name')
  })

  it('handles empty array', () => {
    expect(transformAssignmentFilters([])).toEqual([])
  })

  it('transforms multiple filters at once', () => {
    const filters = [
      { key: 'name', value: 'alice' },
      { key: 'type', value: 'user' },
      { key: 'project', value: 'p1' },
      { key: 'role_name', value: 'Admin' },
    ] as FilterConfig[]
    const result = transformAssignmentFilters(filters)
    expect(result.map((f) => f.key)).toEqual(['principal_name', 'principal_type', 'project_id', 'role_name'])
  })
})

describe('derivePrincipalType', () => {
  it('returns service_account when principal_type is service_account', () => {
    const a = { principal_type: 'service_account' } as unknown as RoleAssignmentRead
    expect(derivePrincipalType(a)).toBe('service_account')
  })

  it('returns group when principal_type is group', () => {
    const a = { principal_type: 'group', group_id: 'g1' } as unknown as RoleAssignmentRead
    expect(derivePrincipalType(a)).toBe('group')
  })

  it('returns group when group_id is present even without principal_type', () => {
    const a = { principal_type: null, group_id: 'g1' } as unknown as RoleAssignmentRead
    expect(derivePrincipalType(a)).toBe('group')
  })

  it('returns user when principal_type is user', () => {
    const a = { principal_type: 'user', group_id: null } as unknown as RoleAssignmentRead
    expect(derivePrincipalType(a)).toBe('user')
  })

  it('returns user as default when no principal_type or group_id', () => {
    const a = { principal_type: null, group_id: null } as unknown as RoleAssignmentRead
    expect(derivePrincipalType(a)).toBe('user')
  })
})

describe('buildPermissionRow', () => {
  const projectAssignment: RoleAssignmentRead = {
    id: 'a1',
    principal_id: 'u1',
    group_id: null,
    principal_type: 'user',
    principal_name: 'alice',
    role_name: 'Admin',
    role_description: 'Full access',
    role_policies: ['policy-a', 'policy-b'],
    project_id: 'p1',
    project_name: 'Project Alpha',
    created_at: '2024-01-01T00:00:00Z',
  } as unknown as RoleAssignmentRead

  const systemAssignment: RoleAssignmentRead = {
    id: 'a2',
    principal_id: null,
    group_id: 'g1',
    principal_type: 'group',
    principal_name: 'Devs',
    role_name: 'Viewer',
    role_description: null,
    role_policies: undefined,
    project_id: null,
    project_name: null,
    created_at: '2024-02-01T00:00:00Z',
  } as unknown as RoleAssignmentRead

  it('builds a project-scoped row', () => {
    const row = buildPermissionRow(projectAssignment)
    expect(row.scopeType).toBe('project')
    expect(row.scopeName).toBe('Project Alpha')
    expect(row.projectId).toBe('p1')
    expect(row.sourceEndpoint).toBe('project-role-assignments')
  })

  it('builds a system-scoped row', () => {
    const row = buildPermissionRow(systemAssignment)
    expect(row.scopeType).toBe('system')
    expect(row.scopeName).toBe('System')
    expect(row.projectId).toBeUndefined()
    expect(row.sourceEndpoint).toBe('role-assignments')
  })

  it('shows a pattern assignment with its pattern as scope, not as System', () => {
    const patternAssignment = {
      ...systemAssignment,
      role_name: 'no-script',
      project_pattern: 'pay*',
    } as unknown as RoleAssignmentRead
    const row = buildPermissionRow(patternAssignment)
    expect(row.scopeType).toBe('project')
    expect(row.scopeName).toBe('Projects matching pay*')
    expect(row.scopeName).not.toBe('System')
    expect(row.projectPattern).toBe('pay*')
    expect(row.projectId).toBeUndefined()
    // Revocation goes through the global endpoint: the row has no single project.
    expect(row.sourceEndpoint).toBe('role-assignments')
  })

  it('leaves projectPattern unset for system and project rows', () => {
    expect(buildPermissionRow(systemAssignment).projectPattern).toBeUndefined()
    expect(buildPermissionRow(projectAssignment).projectPattern).toBeUndefined()
  })

  it('derives principalType from API response', () => {
    expect(buildPermissionRow(projectAssignment).principalType).toBe('user')
    expect(buildPermissionRow(systemAssignment).principalType).toBe('group')
  })

  it('uses principal_id or group_id for principalId', () => {
    expect(buildPermissionRow(projectAssignment).principalId).toBe('u1')
    expect(buildPermissionRow(systemAssignment).principalId).toBe('g1')
  })

  it('falls back principalId to empty string when both are null', () => {
    const noIds = { ...projectAssignment, principal_id: null, group_id: null } as unknown as RoleAssignmentRead
    expect(buildPermissionRow(noIds).principalId).toBe('')
  })

  it('falls back role_description to null', () => {
    expect(buildPermissionRow(projectAssignment).roleDescription).toBe('Full access')
    expect(buildPermissionRow(systemAssignment).roleDescription).toBeNull()
  })

  it('falls back role_policies to empty array', () => {
    expect(buildPermissionRow(projectAssignment).rolePolicies).toEqual(['policy-a', 'policy-b'])
    expect(buildPermissionRow(systemAssignment).rolePolicies).toEqual([])
  })

  it('falls back project_name to project_id when name is null', () => {
    const noName = { ...projectAssignment, project_name: null } as unknown as RoleAssignmentRead
    expect(buildPermissionRow(noName).scopeName).toBe('p1')
  })

  it('copies id, principalName, assignmentType, assignmentName', () => {
    const row = buildPermissionRow(projectAssignment)
    expect(row.id).toBe('a1')
    expect(row.principalName).toBe('alice')
    expect(row.assignmentType).toBe('role')
    expect(row.assignmentName).toBe('Admin')
  })

  it('handles service_account principal type', () => {
    const sa = {
      ...projectAssignment,
      principal_type: 'service_account',
      principal_id: 'sa-1',
    } as unknown as RoleAssignmentRead
    const row = buildPermissionRow(sa)
    expect(row.principalType).toBe('service_account')
    expect(row.principalId).toBe('sa-1')
  })
})

describe('buildSortParam', () => {
  const sortFields: Record<number, string> = { 0: 'principal_name', 1: 'role_name', 2: 'scope' }

  it('returns ascending sort for mapped field', () => {
    expect(buildSortParam(sortFields, 0, 'fallback', 'asc')).toBe('principal_name')
  })

  it('returns descending sort with dash prefix', () => {
    expect(buildSortParam(sortFields, 1, 'fallback', 'desc')).toBe('-role_name')
  })

  it('falls back to defaultSortField for unmapped index', () => {
    expect(buildSortParam(sortFields, 99, 'fallback', 'asc')).toBe('fallback')
  })

  it('falls back to defaultSortField with desc prefix', () => {
    expect(buildSortParam(sortFields, 99, 'fallback', 'desc')).toBe('-fallback')
  })
})
