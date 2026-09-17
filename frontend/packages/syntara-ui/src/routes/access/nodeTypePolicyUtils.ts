/** Matches built-in deny-template names: `{node_type}:{read|write|execute}:deny`. */
const NODE_TYPE_DENY_POLICY_NAME = /^[^:]+:(read|write|execute):deny$/

export function selectedNodeTypeDenyPolicies(policyNames: readonly string[]): string[] {
  return policyNames.filter((name) => NODE_TYPE_DENY_POLICY_NAME.test(name))
}

export const NODE_TYPE_POLICY_SYSTEM_SCOPE_MESSAGE =
  'Workflow node-type deny policies apply system-wide across all projects. Attach them only to system-scoped roles.'
