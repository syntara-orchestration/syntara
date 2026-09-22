import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../../../types/edge'

import { validatePermissionCheckConnections } from './validatePermissionCheckConnections'

const permissionCheck: Activity = {
  id: 'check_1',
  type: 'permission_check',
  name: 'Was restart allowed',
  parameters: {},
}

const upstream: Activity = { id: 'restart', type: 'http_request', name: 'Restart', parameters: {} }

function edge(id: string, source: string, target: string, sourceHandle?: string): EdgeConnection {
  return { id, source, target, sourceHandle: sourceHandle ?? null }
}

describe('validatePermissionCheckConnections', () => {
  it('returns no errors for other node types', () => {
    expect(validatePermissionCheckConnections([upstream], [])).toEqual([])
  })

  it('accepts exactly one incoming edge and allowed/denied outputs', () => {
    const edges = [
      edge('e1', 'restart', 'check_1'),
      edge('e2', 'check_1', 'ok', 'allowed'),
      edge('e3', 'check_1', 'nope', 'denied'),
    ]

    expect(validatePermissionCheckConnections([upstream, permissionCheck], edges)).toEqual([])
  })

  it('reports a missing incoming edge', () => {
    const errors = validatePermissionCheckConnections([permissionCheck], [])

    expect(errors).toHaveLength(1)
    expect(errors[0]).toMatchObject({
      rule: 'permission-check-connections',
      severity: 'error',
      nodeId: 'check_1',
    })
    expect(errors[0].message).toContain('needs one incoming connection')
  })

  it('reports more than one incoming edge', () => {
    const edges = [edge('e1', 'restart', 'check_1'), edge('e2', 'other', 'check_1')]

    const errors = validatePermissionCheckConnections([permissionCheck], edges)

    expect(errors).toHaveLength(1)
    expect(errors[0].message).toContain('must have exactly one incoming connection, but has 2')
  })

  it('reports outgoing edges on unsupported ports', () => {
    const edges = [edge('e1', 'restart', 'check_1'), edge('e2', 'check_1', 'next', 'true')]

    const errors = validatePermissionCheckConnections([permissionCheck], edges)

    expect(errors).toHaveLength(1)
    expect(errors[0].id).toBe('permission-check-invalid-port-check_1-true')
    expect(errors[0].message).toContain("unsupported port 'true'")
  })

  it('accepts an outgoing edge with no explicit handle', () => {
    const edges = [edge('e1', 'restart', 'check_1'), edge('e2', 'check_1', 'next')]

    expect(validatePermissionCheckConnections([permissionCheck], edges)).toEqual([])
  })

  it('falls back to the node id when the step has no name', () => {
    const unnamed: Activity = { id: 'check_2', type: 'permission_check', parameters: {} }

    const errors = validatePermissionCheckConnections([unnamed], [])

    expect(errors[0].message).toContain('"check_2"')
  })
})
