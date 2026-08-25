import { describe, expect, it } from 'vitest'

import { transformApprovalApprovers } from './workflowDefinitionBuilder'

describe('transformApprovalApprovers', () => {
  it('transforms approver_users from objects to strings', () => {
    const input = {
      approver_users: [
        { id: 1, username: 'alice' },
        { id: 2, username: 'bob' },
      ],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toEqual(['alice', 'bob'])
  })

  it('transforms approver_groups from objects to strings', () => {
    const input = {
      approver_groups: [
        { id: 1, name: 'admins' },
        { id: 2, name: 'developers' },
      ],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_groups).toEqual(['admins', 'developers'])
  })

  it('transforms both users and groups simultaneously', () => {
    const input = {
      approver_users: [{ id: 1, username: 'alice' }],
      approver_groups: [{ id: 1, name: 'admins' }],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toEqual(['alice'])
    expect(result.approver_groups).toEqual(['admins'])
  })

  it('is idempotent - transforms strings to same strings', () => {
    const input = {
      approver_users: ['alice', 'bob'],
      approver_groups: ['admins', 'developers'],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toEqual(['alice', 'bob'])
    expect(result.approver_groups).toEqual(['admins', 'developers'])
  })

  it('handles missing approver fields', () => {
    const input = { other_field: 'value' }

    const result = transformApprovalApprovers(input)

    expect(result).toEqual({ other_field: 'value' })
  })

  it('handles null values gracefully', () => {
    const input = {
      approver_users: null,
      approver_groups: null,
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toBeNull()
    expect(result.approver_groups).toBeNull()
  })

  it('handles undefined values gracefully', () => {
    const input = {
      approver_users: undefined,
      approver_groups: undefined,
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toBeUndefined()
    expect(result.approver_groups).toBeUndefined()
  })

  it('preserves other parameters unchanged', () => {
    const input = {
      approver_users: [{ id: 1, username: 'alice' }],
      timeout: 300,
      message: 'Please approve',
      continue_on_failure: true,
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toEqual(['alice'])
    expect(result.timeout).toBe(300)
    expect(result.message).toBe('Please approve')
    expect(result.continue_on_failure).toBe(true)
  })

  it('handles mixed array types gracefully - objects and strings', () => {
    const input = {
      approver_users: [{ id: 1, username: 'alice' }, 'bob'],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toEqual(['alice', 'bob'])
  })

  it('handles objects without username property', () => {
    const input = {
      approver_users: [
        { id: 1, invalid: 'value' },
        { id: 2, username: 'bob' },
      ],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toEqual(['[object Object]', 'bob'])
  })

  it('handles objects without name property in groups', () => {
    const input = {
      approver_groups: [
        { id: 1, invalid: 'value' },
        { id: 2, name: 'admins' },
      ],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_groups).toEqual(['[object Object]', 'admins'])
  })

  it('handles null in array', () => {
    const input = {
      approver_users: [{ id: 1, username: 'alice' }, null, { id: 2, username: 'bob' }],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toEqual(['alice', 'null', 'bob'])
  })

  it('handles empty arrays', () => {
    const input = {
      approver_users: [],
      approver_groups: [],
    }

    const result = transformApprovalApprovers(input)

    expect(result.approver_users).toEqual([])
    expect(result.approver_groups).toEqual([])
  })

  it('does not mutate the original object', () => {
    const input = {
      approver_users: [{ id: 1, username: 'alice' }],
    }

    const result = transformApprovalApprovers(input)

    expect(input.approver_users).toEqual([{ id: 1, username: 'alice' }])
    expect(result.approver_users).toEqual(['alice'])
    expect(result).not.toBe(input)
  })
})
