import { describe, expect, it } from 'vitest'

import { filterPoliciesForRoleSelect, mergeSelectAll, type PolicySelectListItem } from './policySelectConstants'

const globalPolicy: PolicySelectListItem = {
  name: 'workflow-admin',
  is_project_eligible: false,
}

const projectBuiltinPolicy: PolicySelectListItem = {
  name: 'policy:update:project',
  is_project_eligible: true,
}

const projectCustomPolicy: PolicySelectListItem = {
  name: 'custom-project-policy',
  project_id: 'proj-1',
  is_project_eligible: true,
}

describe('filterPoliciesForRoleSelect', () => {
  it('returns only non-project-eligible policies for global roles', () => {
    expect(filterPoliciesForRoleSelect([globalPolicy, projectBuiltinPolicy, projectCustomPolicy], {})).toEqual([
      globalPolicy,
    ])
  })

  it('returns only project-eligible policies when projectEligible is true', () => {
    expect(
      filterPoliciesForRoleSelect([globalPolicy, projectBuiltinPolicy, projectCustomPolicy], {
        projectEligible: true,
      })
    ).toEqual([projectBuiltinPolicy, projectCustomPolicy])
  })

  it('returns policies for the selected project when scopeProjectId is set', () => {
    expect(
      filterPoliciesForRoleSelect([globalPolicy, projectBuiltinPolicy, projectCustomPolicy], {
        scopeProjectId: 'proj-1',
      })
    ).toEqual([globalPolicy, projectBuiltinPolicy, projectCustomPolicy])
  })
})

describe('mergeSelectAll', () => {
  it('merges current selection with new option names without duplicates', () => {
    expect(mergeSelectAll(['a', 'b'], ['b', 'c', 'd'])).toEqual(['a', 'b', 'c', 'd'])
  })

  it('returns only new names when nothing is selected', () => {
    expect(mergeSelectAll([], ['x', 'y'])).toEqual(['x', 'y'])
  })

  it('preserves existing selection when option list is empty', () => {
    expect(mergeSelectAll(['a'], [])).toEqual(['a'])
  })
})
