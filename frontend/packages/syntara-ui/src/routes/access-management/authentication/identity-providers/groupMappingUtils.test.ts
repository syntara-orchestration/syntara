import { describe, expect, it } from 'vitest'

import {
  buildSavePayload,
  nextKey,
  processDiscoveredGroups,
  searchGroups,
  toFormEntries,
  validateGroupJmespathExpression,
  type GroupMappingConfig,
  type GroupMappingEntry,
  type NexusGroup,
} from './groupMappingUtils'

describe('groupMappingUtils', () => {
  describe('nextKey', () => {
    it('returns unique keys', () => {
      const key1 = nextKey()
      const key2 = nextKey()
      expect(key1).toMatch(/^entry-.+$/)
      expect(key2).toMatch(/^entry-.+$/)
      expect(key1).not.toBe(key2)
    })
  })

  describe('searchGroups', () => {
    it('extracts groups from claims using JMESPath expression', () => {
      const claims = { groups: ['admin', 'users', 'devs'] }
      const result = searchGroups(claims, 'groups[*]')
      expect(result).toEqual(['admin', 'users', 'devs'])
    })

    it('returns empty array when expression matches nothing', () => {
      const claims = { roles: ['admin'] }
      const result = searchGroups(claims, 'groups[*]')
      expect(result).toEqual([])
    })

    it('returns empty array for invalid expression', () => {
      const claims = { groups: ['admin'] }
      const result = searchGroups(claims, '.[invalid')
      expect(result).toEqual([])
    })

    it('wraps non-array results as single-element array', () => {
      const claims = { group: 'admin' }
      const result = searchGroups(claims, 'group')
      expect(result).toEqual(['admin'])
    })

    it('stringifies non-string values', () => {
      const claims = { groups: [{ name: 'admin' }] }
      const result = searchGroups(claims, 'groups[*]')
      expect(result).toEqual(['{"name":"admin"}'])
    })

    it('filters null/undefined values from results', () => {
      const claims = { groups: ['admin', null, 'users', undefined] }
      const result = searchGroups(claims, 'groups[*]')
      expect(result).toEqual(['admin', 'users'])
    })

    it('returns empty array when claims is empty', () => {
      const result = searchGroups({}, 'groups[*]')
      expect(result).toEqual([])
    })
  })

  describe('validateGroupJmespathExpression', () => {
    it('returns null for valid syntax', () => {
      expect(validateGroupJmespathExpression('groups[*]')).toBeNull()
    })

    it('returns an error message for invalid syntax', () => {
      expect(validateGroupJmespathExpression('groups[[[*]')).toBe(
        "Invalid group extraction expression: 'groups[[[*]' is not a valid JMESPath expression"
      )
    })
  })

  describe('toFormEntries', () => {
    it('converts API config to form entries', () => {
      const config: GroupMappingConfig = {
        group_jmespath_expression: 'groups[*]',
        group_mapping_entries: [
          { idp_group_value: 'admin', mapped_group_id: 'g1' },
          { idp_group_value: 'users', mapped_group_id: 'g2' },
        ],
      }
      const result = toFormEntries(config)
      expect(result).toHaveLength(2)
      expect(result[0]).toMatchObject({ idpGroupValue: 'admin', nexusGroupId: 'g1' })
      expect(result[1]).toMatchObject({ idpGroupValue: 'users', nexusGroupId: 'g2' })
      expect(result[0].key).toBeTruthy()
    })

    it('returns empty array for null config', () => {
      expect(toFormEntries(null)).toEqual([])
    })

    it('returns empty array for undefined config', () => {
      expect(toFormEntries(undefined)).toEqual([])
    })

    it('returns empty array for config with no entries', () => {
      const config: GroupMappingConfig = { group_jmespath_expression: 'groups[*]' }
      expect(toFormEntries(config)).toEqual([])
    })
  })

  describe('buildSavePayload', () => {
    it('builds payload with filtered entries', () => {
      const providerConfig = {
        provider_type: 'oidc' as const,
        issuer_url: 'https://example.com',
        client_id: 'client-123',
        redirect_uri: 'http://localhost/callback',
      }
      const entries: GroupMappingEntry[] = [
        { key: 'k1', idpGroupValue: 'admin', nexusGroupId: 'g1' },
        { key: 'k2', idpGroupValue: '', nexusGroupId: '' },
        { key: 'k3', idpGroupValue: 'users', nexusGroupId: 'g2' },
      ]
      const result = buildSavePayload(providerConfig, 'groups[*]', entries)

      expect(result.configuration).toMatchObject({
        issuer_url: 'https://example.com',
        provider_type: 'oidc',
        group_jmespath_expression: 'groups[*]',
        group_mapping_entries: [
          { idp_group_value: 'admin', mapped_group_id: 'g1' },
          { idp_group_value: 'users', mapped_group_id: 'g2' },
        ],
      })
    })

    it('filters entries where idpGroupValue is empty', () => {
      const entries: GroupMappingEntry[] = [{ key: 'k1', idpGroupValue: '', nexusGroupId: 'g1' }]
      const result = buildSavePayload(
        { issuer_url: 'https://example.com', client_id: 'test-client', redirect_uri: 'http://localhost/callback' },
        'groups[*]',
        entries
      )
      expect(result.configuration?.group_mapping_entries).toEqual([])
    })

    it('filters entries where nexusGroupId is empty', () => {
      const entries: GroupMappingEntry[] = [{ key: 'k1', idpGroupValue: 'admin', nexusGroupId: '' }]
      const result = buildSavePayload(
        { issuer_url: 'https://example.com', client_id: 'test-client', redirect_uri: 'http://localhost/callback' },
        'groups[*]',
        entries
      )
      expect(result.configuration?.group_mapping_entries).toEqual([])
    })
  })

  describe('processDiscoveredGroups', () => {
    const nexusGroups: NexusGroup[] = [
      { id: 'g1', name: 'admin' },
      { id: 'g2', name: 'users' },
      { id: 'g3', name: 'devs', description: 'Developers' },
    ]

    it('returns warning when no groups found', () => {
      const result = processDiscoveredGroups({}, 'groups[*]', [], nexusGroups)
      expect(result.variant).toBe('warning')
      expect(result.message).toContain('No groups found')
      expect(result.newEntries).toEqual([])
    })

    it('auto-matches discovered groups to nexus groups by name', () => {
      const claims = { groups: ['admin', 'users'] }
      const result = processDiscoveredGroups(claims, 'groups[*]', [], nexusGroups)

      expect(result.variant).toBe('success')
      expect(result.newEntries).toHaveLength(2)
      expect(result.newEntries[0]).toMatchObject({ idpGroupValue: 'admin', nexusGroupId: 'g1' })
      expect(result.newEntries[1]).toMatchObject({ idpGroupValue: 'users', nexusGroupId: 'g2' })
      expect(result.message).toContain('Discovered 2 group(s)')
      expect(result.message).toContain('2 matched')
    })

    it('preserves existing entries for discovered groups', () => {
      const existingEntries: GroupMappingEntry[] = [{ key: 'existing-1', idpGroupValue: 'admin', nexusGroupId: 'g3' }]
      const claims = { groups: ['admin', 'users'] }
      const result = processDiscoveredGroups(claims, 'groups[*]', existingEntries, nexusGroups)

      expect(result.newEntries).toHaveLength(2)
      // Existing entry preserved with its key and custom mapping
      expect(result.newEntries[0]).toMatchObject({ key: 'existing-1', idpGroupValue: 'admin', nexusGroupId: 'g3' })
      // New entry auto-matched
      expect(result.newEntries[1]).toMatchObject({ idpGroupValue: 'users', nexusGroupId: 'g2' })
    })

    it('keeps manually added entries not in discovered groups', () => {
      const existingEntries: GroupMappingEntry[] = [
        { key: 'manual-1', idpGroupValue: 'custom-group', nexusGroupId: 'g1' },
      ]
      const claims = { groups: ['admin'] }
      const result = processDiscoveredGroups(claims, 'groups[*]', existingEntries, nexusGroups)

      expect(result.newEntries).toHaveLength(2)
      expect(result.newEntries[0]).toMatchObject({ idpGroupValue: 'admin', nexusGroupId: 'g1' })
      expect(result.newEntries[1]).toMatchObject({ idpGroupValue: 'custom-group', nexusGroupId: 'g1' })
    })

    it('returns success without match count when no auto-matches', () => {
      const claims = { groups: ['unknown-group'] }
      const result = processDiscoveredGroups(claims, 'groups[*]', [], nexusGroups)

      expect(result.variant).toBe('success')
      expect(result.message).toBe('Discovered 1 group(s).')
      expect(result.newEntries[0]).toMatchObject({ idpGroupValue: 'unknown-group', nexusGroupId: '' })
    })

    it('handles nexus groups without id or name', () => {
      const groups: NexusGroup[] = [
        { id: undefined, name: 'no-id' },
        { id: 'g-no-name', name: undefined },
      ]
      const claims = { groups: ['no-id', 'no-name-match'] }
      const result = processDiscoveredGroups(claims, 'groups[*]', [], groups)

      // Neither should auto-match because id or name is missing
      expect(result.newEntries[0].nexusGroupId).toBe('')
      expect(result.newEntries[1].nexusGroupId).toBe('')
    })
  })
})
