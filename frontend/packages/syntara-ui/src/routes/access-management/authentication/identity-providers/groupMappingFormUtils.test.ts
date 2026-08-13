import { describe, expect, it } from 'vitest'

import {
  buildGroupMappingFormDefaultValues,
  groupMappingFormPageTitle,
  initialGroupMappingFormEntries,
  parseGroupMappingFormSearch,
  signInAlertTitle,
} from './groupMappingFormUtils'

describe('groupMappingFormUtils', () => {
  describe('signInAlertTitle', () => {
    it('returns titles for each alert variant', () => {
      expect(signInAlertTitle('success')).toBe('Groups discovered')
      expect(signInAlertTitle('danger')).toBe('Sign-in failed')
      expect(signInAlertTitle('warning')).toBe('No groups found')
    })
  })
  describe('groupMappingFormPageTitle', () => {
    it('returns Add when there are no server mappings', () => {
      expect(groupMappingFormPageTitle(false, false)).toBe('Add group mapping')
    })

    it('returns Add when isAddFlow is true even with server mappings', () => {
      expect(groupMappingFormPageTitle(true, true)).toBe('Add group mapping')
    })

    it('returns Edit when server mappings exist and not add flow', () => {
      expect(groupMappingFormPageTitle(true, false)).toBe('Edit group mapping')
    })
  })

  describe('parseGroupMappingFormSearch', () => {
    it('parses new and discover query params', () => {
      expect(parseGroupMappingFormSearch('?new=1&discover=1')).toEqual({
        isAddFlow: true,
        openDiscoverOnMount: true,
      })
    })

    it('returns false flags for an empty search string', () => {
      expect(parseGroupMappingFormSearch('')).toEqual({
        isAddFlow: false,
        openDiscoverOnMount: false,
      })
    })
  })

  describe('initialGroupMappingFormEntries', () => {
    it('returns one blank row when there are no server entries', () => {
      const entries = initialGroupMappingFormEntries(null)
      expect(entries).toHaveLength(1)
      expect(entries[0]?.idpGroupValue).toBe('')
    })

    it('returns server entries when present', () => {
      const entries = initialGroupMappingFormEntries({
        group_mapping_entries: [{ idp_group_value: 'admins', mapped_group_id: 'g1' }],
      })
      expect(entries).toHaveLength(1)
      expect(entries[0]?.idpGroupValue).toBe('admins')
    })
  })

  describe('buildGroupMappingFormDefaultValues', () => {
    it('uses server expression and entries when present', () => {
      expect(
        buildGroupMappingFormDefaultValues(
          {
            group_jmespath_expression: 'groups[?@]',
            group_mapping_entries: [{ idp_group_value: 'admins', mapped_group_id: 'g1' }],
          },
          'groups[*]'
        )
      ).toEqual({
        expression: 'groups[?@]',
        entries: [{ idpGroupValue: 'admins', mappedGroupId: 'g1' }],
      })
    })

    it('falls back to default expression when server has none', () => {
      expect(buildGroupMappingFormDefaultValues(null, 'groups[*]')).toEqual({
        expression: 'groups[*]',
        entries: [{ idpGroupValue: '', mappedGroupId: '' }],
      })
    })
  })
})
