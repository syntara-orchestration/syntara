/** Built-in deny-template policy names use this prefix (see backend workflow_node_type_policies). */
export const WORKFLOW_NODE_TYPE_POLICY_PREFIX = 'workflow_node_type:'

export function selectedNodeTypeDenyPolicies(policyNames: readonly string[]): string[] {
  return policyNames.filter((name) => name.startsWith(WORKFLOW_NODE_TYPE_POLICY_PREFIX))
}

export const NODE_TYPE_POLICY_SYSTEM_SCOPE_MESSAGE =
  'Workflow node-type deny policies apply system-wide across all projects. Attach them only to system-scoped roles.'
