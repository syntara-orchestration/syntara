import type { NodeKindsAPI } from '@syntara/contracts'

export type StepTypePermissionRead = NodeKindsAPI['components']['schemas']['StepTypePermissionRead']
export type StepTypeBlockedBy = NodeKindsAPI['components']['schemas']['StepTypeBlockedBy']

/** Registry grouping that mirrors the backend `node_kinds_router.py` categories. */
type NodeKindCategory = 'trigger' | 'flow_control' | 'action'

/** Label shown in tooltips, mirroring the backend `node_kind_display_label`. */
const LABELS: Record<string, string> = {
  manual_trigger: 'Manual trigger',
  scheduled_trigger: 'Schedule trigger',
  webhook_trigger: 'Webhook trigger',
  eda_trigger: 'Event-Driven Ansible trigger',
  condition: 'Conditional',
  converge: 'Converge',
  loop: 'Loop',
  switch: 'Switch',
  wait: 'Wait',
  aap_job_template: 'AAP Job Template',
  aap_workflow_job_template: 'AAP Workflow Template',
  agentic: 'Task Agent',
  approval: 'Approval',
  http_request: 'REST API',
  script: 'Script',
}

/** Every grantable step type with its category, in backend `NodeType` order. */
export const STEP_TYPES: ReadonlyArray<{ kind: string; category: NodeKindCategory }> = [
  { kind: 'manual_trigger', category: 'trigger' },
  { kind: 'scheduled_trigger', category: 'trigger' },
  { kind: 'webhook_trigger', category: 'trigger' },
  { kind: 'eda_trigger', category: 'trigger' },
  { kind: 'condition', category: 'flow_control' },
  { kind: 'converge', category: 'flow_control' },
  { kind: 'loop', category: 'flow_control' },
  { kind: 'switch', category: 'flow_control' },
  { kind: 'wait', category: 'flow_control' },
  { kind: 'aap_job_template', category: 'action' },
  { kind: 'aap_workflow_job_template', category: 'action' },
  { kind: 'agentic', category: 'action' },
  { kind: 'approval', category: 'action' },
  { kind: 'http_request', category: 'action' },
  { kind: 'script', category: 'action' },
]

/**
 * Kinds the mock principal may not author anywhere (a global deny).
 * Mutated in place by demo scripts so the builder palette can be exercised
 * without a real deny-effect policy.
 */
export const writeDeniedNodeKinds: string[] = []

/**
 * Kinds the mock principal may not author in one project (a project deny),
 * keyed by project name or UUID. Takes precedence over the global list.
 */
export const projectWriteDeniedNodeKinds: Record<string, string[]> = {}

function blockedBy(
  kind: string,
  reason: 'explicit_deny',
  policy: string,
  scope: string,
  project: string | null
): StepTypeBlockedBy {
  return { kind, label: LABELS[kind] ?? kind, reason, policy, scope, project }
}

/** Project the step-type verdicts for the calling principal. */
export function nodeKindsForCaller(projectName: string | null): StepTypePermissionRead[] {
  return STEP_TYPES.map(({ kind, category }) => {
    const projectDenied = projectName != null && (projectWriteDeniedNodeKinds[projectName] ?? []).includes(kind)
    const globallyDenied = writeDeniedNodeKinds.includes(kind)
    if (!projectDenied && !globallyDenied) {
      return { kind, category, can_write: true, blocked_by: null }
    }
    return {
      kind,
      category,
      can_write: false,
      blocked_by: projectDenied
        ? blockedBy(kind, 'explicit_deny', `no-${kind.replaceAll('_', '-')}-in-${projectName}`, 'project', projectName)
        : blockedBy(kind, 'explicit_deny', `no-${kind.replaceAll('_', '-')}-anywhere`, 'any', null),
    }
  })
}
