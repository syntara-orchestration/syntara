import { describe, expect, it } from 'vitest'

import { BUILTIN_AUTHENTICATED_GROUP_NAME, excludeAuthenticatedGroup } from './adminConstants'

describe('excludeAuthenticatedGroup', () => {
  it('removes the authenticated group from the list', () => {
    const groups = [{ name: 'users' }, { name: BUILTIN_AUTHENTICATED_GROUP_NAME }, { name: 'admins' }]

    expect(excludeAuthenticatedGroup(groups)).toStrictEqual([{ name: 'users' }, { name: 'admins' }])
  })

  it('returns the list unchanged when the authenticated group is absent', () => {
    const groups = [{ name: 'users' }, { name: 'admins' }]

    expect(excludeAuthenticatedGroup(groups)).toStrictEqual(groups)
  })

  it('returns an empty array when given an empty list', () => {
    expect(excludeAuthenticatedGroup([])).toStrictEqual([])
  })
})
