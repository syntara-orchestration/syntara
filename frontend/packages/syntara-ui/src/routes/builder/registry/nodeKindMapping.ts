import { ActivityTypeEnum, TriggerTypeEnum } from '@syntara/contracts'

import { RegistryNodeId } from '../../../constants'

/**
 * Registry node id → backend node kind (a `NodeType` value).
 *
 * The builder registry identifies palette entries by its own ids
 * (`action-api`, `logic-condition`, …) while the authorization layer and the
 * kill switch speak in node kinds (`http_request`, `condition`, …). This map is
 * the single translation point between the two.
 *
 * Container entries such as `trigger`, `action`, `logic` and `aap-execution`
 * have no kind of their own — they only open a subtype list, so their gating is
 * derived from their subtypes.
 */
export const NODE_KIND_BY_REGISTRY_ID: Readonly<Record<string, string>> = {
  [RegistryNodeId.TRIGGER_MANUAL]: TriggerTypeEnum.MANUAL_TRIGGER,
  [RegistryNodeId.TRIGGER_SCHEDULED]: TriggerTypeEnum.SCHEDULED,
  [RegistryNodeId.TRIGGER_WEBHOOK]: TriggerTypeEnum.WEBHOOK_TRIGGER,
  [RegistryNodeId.TRIGGER_EDA]: TriggerTypeEnum.EDA_TRIGGER,
  [RegistryNodeId.ACTION_SCRIPT]: ActivityTypeEnum.SCRIPT,
  [RegistryNodeId.ACTION_API]: ActivityTypeEnum.HTTP_REQUEST,
  [RegistryNodeId.APPROVAL]: ActivityTypeEnum.APPROVAL,
  [RegistryNodeId.AGENT]: ActivityTypeEnum.AGENTIC,
  [RegistryNodeId.LOGIC_CONDITION]: ActivityTypeEnum.CONDITION,
  [RegistryNodeId.LOGIC_CONVERGE]: ActivityTypeEnum.CONVERGE,
  [RegistryNodeId.LOGIC_LOOP]: ActivityTypeEnum.LOOP,
  [RegistryNodeId.LOGIC_SWITCH]: ActivityTypeEnum.SWITCH,
  [RegistryNodeId.LOGIC_WAIT]: ActivityTypeEnum.WAIT,
  [RegistryNodeId.LOGIC_PERMISSION_CHECK]: ActivityTypeEnum.PERMISSION_CHECK,
  [RegistryNodeId.ACTION_MCP_TOOL]: ActivityTypeEnum.MCP_TOOL,
  [RegistryNodeId.AAP_JOB_TEMPLATE]: ActivityTypeEnum.AAP_JOB_TEMPLATE,
  [RegistryNodeId.AAP_WORKFLOW_TEMPLATE]: ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE,
}

/** Registry id prefixes that name a palette family rather than part of the kind. */
const FAMILY_PREFIXES = ['trigger-', 'action-', 'logic-', 'flow-', 'aap-']

function normalizeRegistryId(registryNodeId: string): string {
  const withoutFamily = FAMILY_PREFIXES.reduce(
    (id, prefix) => (id.startsWith(prefix) ? id.slice(prefix.length) : id),
    registryNodeId
  )
  return withoutFamily.replaceAll('-', '_')
}

/**
 * Resolve the backend node kind a palette entry creates.
 *
 * Entries registered after this map was written are resolved by normalizing the
 * registry id (`logic-permission-check` → `permission_check`) and accepting the
 * result only when the backend registry knows that kind, so a newly registered
 * node kind is gated without a second edit here.
 *
 * @param registryNodeId Registry id of the palette entry (or subtype).
 * @param knownKinds Kinds reported by `GET /node_kinds`.
 * @returns The node kind, or `null` for container entries and unknown ids.
 */
export function resolveNodeKind(registryNodeId: string, knownKinds: ReadonlySet<string>): string | null {
  const mapped = NODE_KIND_BY_REGISTRY_ID[registryNodeId]
  if (mapped) return mapped

  const normalized = normalizeRegistryId(registryNodeId)
  return knownKinds.has(normalized) ? normalized : null
}
