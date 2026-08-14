import type { IdentityProvidersAPI } from '@syntara/contracts'
import jmespath from 'jmespath'

import { generateUUID } from '../../../../utils/generateUUID'

const PROVIDER_TYPE_OIDC = 'oidc' as const

export type OIDCConfigurationResponse = IdentityProvidersAPI.components['schemas']['OIDCConfigurationResponse']
type IdentityProviderUpdate = IdentityProvidersAPI.components['schemas']['IdentityProviderUpdate']

export type GroupMappingEntry = {
  key: string
  idpGroupValue: string
  nexusGroupId: string
}

/** Form/API row shape without react-hook-form field-array id */
export type GroupMappingFormEntry = Pick<GroupMappingEntry, 'idpGroupValue' | 'nexusGroupId'>

export type NexusGroup = {
  id?: string
  name?: string
  description?: string | null
}

export function nextKey(): string {
  return `entry-${generateUUID()}`
}

export function searchGroups(claims: Record<string, unknown>, expression: string): string[] {
  let result: unknown
  try {
    result = jmespath.search(claims, expression) as unknown
  } catch {
    return []
  }
  if (result == null) return []
  const items = Array.isArray(result) ? result : [result]
  return items.filter((v) => v != null).map((v) => (typeof v === 'string' ? v : JSON.stringify(v)))
}

/** Returns null when valid, or an error message when the expression is invalid JMESPath syntax. */
export function validateGroupJmespathExpression(expression: string): string | null {
  try {
    jmespath.search({}, expression)
    return null
  } catch {
    return `Invalid group extraction expression: '${expression}' is not a valid JMESPath expression`
  }
}

export type GroupMappingConfig = {
  group_jmespath_expression?: string | null
  group_mapping_entries?: { idp_group_value: string; mapped_group_id: string }[]
}

type GroupMappingConfigSource = {
  group_jmespath_expression?: string | null
  group_mapping_entries?: { idp_group_value: string; mapped_group_id: string }[]
}

export function buildGroupMappingConfig(config: GroupMappingConfigSource | undefined): GroupMappingConfig | null {
  if (!config?.group_jmespath_expression && !config?.group_mapping_entries?.length) return null
  return {
    group_jmespath_expression: config.group_jmespath_expression,
    group_mapping_entries: config.group_mapping_entries,
  }
}

export function hasServerMappingEntries(groupMapping: GroupMappingConfig | null | undefined): boolean {
  return (groupMapping?.group_mapping_entries?.length ?? 0) > 0
}

export function toFormEntries(config: GroupMappingConfig | null | undefined): GroupMappingEntry[] {
  if (!config?.group_mapping_entries) return []
  return config.group_mapping_entries.map((e) => ({
    key: nextKey(),
    idpGroupValue: e.idp_group_value,
    nexusGroupId: e.mapped_group_id,
  }))
}

export function buildSavePayload(
  providerConfig: OIDCConfigurationResponse,
  expression: string,
  entries: GroupMappingFormEntry[]
): IdentityProviderUpdate {
  return {
    configuration: {
      ...providerConfig,
      provider_type: PROVIDER_TYPE_OIDC,
      issuer_url: providerConfig.issuer_url ?? '',
      client_id: providerConfig.client_id ?? '',
      redirect_uri: providerConfig.redirect_uri ?? '',
      group_jmespath_expression: expression,
      group_mapping_entries: entries
        .filter((e) => e.idpGroupValue && e.nexusGroupId)
        .map((e) => ({ idp_group_value: e.idpGroupValue, mapped_group_id: e.nexusGroupId })),
    },
  }
}

export function processDiscoveredGroups(
  claims: Record<string, unknown>,
  expression: string,
  entries: GroupMappingFormEntry[],
  nexusGroups: NexusGroup[]
): { newEntries: GroupMappingFormEntry[]; message: string; variant: 'success' | 'warning' } {
  const groups = searchGroups(claims, expression)

  if (groups.length === 0) {
    return {
      newEntries: entries,
      message:
        'No groups found. Check that the provider template is correct or adjust the Group Extraction Expression in Advanced settings.',
      variant: 'warning',
    }
  }

  const nexusGroupByName = new Map<string, string>()
  for (const g of nexusGroups) {
    if (g.name && g.id) nexusGroupByName.set(g.name, g.id)
  }

  const existingByValue = new Map<string, GroupMappingFormEntry>()
  for (const e of entries) {
    existingByValue.set(e.idpGroupValue, e)
  }

  const discoveredEntries = groups.map((g) => {
    const existing = existingByValue.get(g)
    if (existing) {
      existingByValue.delete(g)
      return existing
    }
    return { idpGroupValue: g, nexusGroupId: nexusGroupByName.get(g) ?? '' }
  })

  const newEntries = [...discoveredEntries, ...existingByValue.values()]
  const autoMatched = newEntries.filter((e) => e.nexusGroupId).length
  const message =
    autoMatched > 0
      ? `Discovered ${String(groups.length)} group(s). ${String(autoMatched)} matched to groups.`
      : `Discovered ${String(groups.length)} group(s).`

  return { newEntries, message, variant: 'success' }
}
