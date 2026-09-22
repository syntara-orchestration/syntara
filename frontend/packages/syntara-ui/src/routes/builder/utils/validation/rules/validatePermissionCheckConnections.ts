import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

import type { EdgeConnection } from '../../../types/edge'
import type { ValidationError } from '../types'

const RULE_NAME = 'permission-check-connections'

/** The only source handles a permission check step may use. */
const ALLOWED_SOURCE_HANDLES: ReadonlySet<string> = new Set([EdgeHandleEnum.ALLOWED, EdgeHandleEnum.DENIED])

function displayName(node: Activity): string {
  return node.name ?? node.id
}

/**
 * Validates the structural rules the backend enforces for `permission_check` steps:
 *
 * - exactly one incoming edge (the step being checked)
 * - outgoing edges only on the `allowed` and `denied` ports
 */
export function validatePermissionCheckConnections(activities: Activity[], edges: EdgeConnection[]): ValidationError[] {
  const errors: ValidationError[] = []
  const permissionCheckNodes = activities.filter((activity) => activity.type === ActivityTypeEnum.PERMISSION_CHECK)

  for (const node of permissionCheckNodes) {
    const incoming = edges.filter((edge) => edge.target === node.id)

    if (incoming.length === 0) {
      errors.push({
        id: `permission-check-missing-input-${node.id}`,
        severity: 'error',
        rule: RULE_NAME,
        message: `Permission check "${displayName(node)}" needs one incoming connection`,
        nodeId: node.id,
        suggestion: 'Connect the step whose permission should be checked to this permission check step',
      })
    } else if (incoming.length > 1) {
      errors.push({
        id: `permission-check-too-many-inputs-${node.id}`,
        severity: 'error',
        rule: RULE_NAME,
        message: `Permission check "${displayName(node)}" must have exactly one incoming connection, but has ${String(incoming.length)}`,
        nodeId: node.id,
        suggestion: 'Remove the extra incoming connections so only the step being checked remains',
      })
    }

    const invalidPorts = edges
      .filter((edge) => edge.source === node.id)
      .map((edge) => edge.sourceHandle)
      .filter((handle): handle is string => typeof handle === 'string' && !ALLOWED_SOURCE_HANDLES.has(handle))

    for (const handle of invalidPorts) {
      errors.push({
        id: `permission-check-invalid-port-${node.id}-${handle}`,
        severity: 'error',
        rule: RULE_NAME,
        message: `Permission check "${displayName(node)}" has an outgoing connection on the unsupported port '${handle}'`,
        nodeId: node.id,
        suggestion: "Connect downstream steps from the 'Allowed' or 'Denied' handle only",
      })
    }
  }

  return errors
}
