import type { GroupMappingConfig } from './groupMappingUtils'
import { toFormEntries } from './groupMappingUtils'

export function signInAlertTitle(variant: string): string {
  if (variant === 'success') return 'Groups discovered'
  if (variant === 'danger') return 'Sign-in failed'
  return 'No groups found'
}

export function groupMappingFormPageTitle(hasServerMappings: boolean, isAddFlow: boolean): string {
  if (isAddFlow || !hasServerMappings) return 'Add group mapping'
  return 'Edit group mapping'
}

export function parseGroupMappingFormSearch(search: string): { isAddFlow: boolean; openDiscoverOnMount: boolean } {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  return {
    isAddFlow: params.get('new') === '1',
    openDiscoverOnMount: params.get('discover') === '1',
  }
}

export type GroupMappingFormEntry = {
  idpGroupValue: string
  mappedGroupId: string
}

export function initialGroupMappingFormEntries(
  groupMapping: GroupMappingConfig | null | undefined
): GroupMappingFormEntry[] {
  const fromServer = toFormEntries(groupMapping)
  if (fromServer.length > 0) {
    return fromServer.map(({ idpGroupValue, mappedGroupId }) => ({ idpGroupValue, mappedGroupId }))
  }
  return [{ idpGroupValue: '', mappedGroupId: '' }]
}

export function buildGroupMappingFormDefaultValues(
  groupMapping: GroupMappingConfig | null | undefined,
  defaultExpression: string | null
): { expression: string; entries: GroupMappingFormEntry[] } {
  return {
    expression: groupMapping?.group_jmespath_expression ?? defaultExpression ?? 'groups[*]',
    entries: initialGroupMappingFormEntries(groupMapping),
  }
}
