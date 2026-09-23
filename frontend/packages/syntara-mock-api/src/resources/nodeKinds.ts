import type { NodeKindsAPI } from '@syntara/contracts'

type NodeKindRead = NodeKindsAPI['components']['schemas']['NodeKindRead']
type NodeKindCategory = NodeKindsAPI['components']['schemas']['NodeKindCategory']
type NodeAttributeRead = NodeKindsAPI['components']['schemas']['NodeAttributeRead']

/** Actions a deny-effect policy may target, per category (mirrors node_kinds.py). */
const DENIABLE_ACTIONS: Record<NodeKindCategory, string[]> = {
  trigger: ['write'],
  flow_control: [],
  action: ['write', 'execute'],
}

/** Flow control kinds are required by the engine, so they can never be switched off. */
function isSwitchable(category: NodeKindCategory): boolean {
  return category !== 'flow_control'
}

const ATTRIBUTES_BY_KIND: Record<string, NodeAttributeRead[]> = {
  script: [{ name: 'language', allowed_values: ['python', 'bash'] }],
  http_request: [{ name: 'method', allowed_values: ['get', 'post', 'put', 'patch', 'delete'] }],
  mcp_tool: [
    { name: 'tool_name', allowed_values: null },
    { name: 'integration_id', allowed_values: null },
  ],
  aap_job_template: [
    { name: 'job_template_name', allowed_values: null },
    { name: 'integration_id', allowed_values: null },
  ],
  aap_workflow_job_template: [
    { name: 'workflow_job_template_name', allowed_values: null },
    { name: 'integration_id', allowed_values: null },
  ],
  agentic: [{ name: 'model', allowed_values: null }],
  internal_activity: [
    {
      name: 'activity',
      allowed_values: [
        'document_conversion',
        'invocation_execution',
        'integration_health_check',
        'integration_resource_discovery',
      ],
    },
  ],
}

function nodeKind(kind: string, category: NodeKindCategory): NodeKindRead {
  return {
    kind,
    category,
    enabled: true,
    switchable: isSwitchable(category),
    deniable_actions: DENIABLE_ACTIONS[category],
    can_write: true,
    attributes: ATTRIBUTES_BY_KIND[kind] ?? [],
  }
}

/** Every registered node kind, in backend `NodeType` declaration order. */
export const nodeKinds: NodeKindRead[] = [
  nodeKind('manual_trigger', 'trigger'),
  nodeKind('scheduled_trigger', 'trigger'),
  nodeKind('webhook_trigger', 'trigger'),
  nodeKind('eda_trigger', 'trigger'),
  nodeKind('condition', 'flow_control'),
  nodeKind('converge', 'flow_control'),
  nodeKind('loop', 'flow_control'),
  nodeKind('switch', 'flow_control'),
  nodeKind('wait', 'flow_control'),
  nodeKind('aap_job_template', 'action'),
  nodeKind('aap_workflow_job_template', 'action'),
  nodeKind('agentic', 'action'),
  nodeKind('approval', 'action'),
  nodeKind('http_request', 'action'),
  nodeKind('internal_activity', 'action'),
  nodeKind('mcp_tool', 'action'),
  nodeKind('script', 'action'),
]

/**
 * Kinds switched off platform-wide (the `workflows.disabled_node_kinds` setting).
 * Mutated in place by the kill-switch handler so the mock persists within a session.
 */
export const disabledNodeKinds: string[] = []

/**
 * Kinds the mock principal may not introduce into a workflow.
 * Drives `can_write: false` so the builder palette can be exercised without a
 * real deny-effect policy.
 */
export const writeDeniedNodeKinds: string[] = []

/** Look up a kind by its `NodeType` value. */
export function findNodeKind(kind: string): NodeKindRead | undefined {
  return nodeKinds.find((entry) => entry.kind === kind)
}

/** Project the registry for a caller, applying the kill switch and write denials. */
export function nodeKindsForCaller(): NodeKindRead[] {
  return nodeKinds.map((entry) => ({
    ...entry,
    enabled: !disabledNodeKinds.includes(entry.kind),
    can_write: !writeDeniedNodeKinds.includes(entry.kind),
  }))
}
