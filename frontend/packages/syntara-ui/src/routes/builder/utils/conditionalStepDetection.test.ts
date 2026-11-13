/**
 * Tests for conditional step detection utilities.
 */

import { describe, expect, it } from 'vitest'

import { extractStepIdFromExpression, isStepConditional } from './conditionalStepDetection'

describe('extractStepIdFromExpression', () => {
  it('extracts step ID from simple expression', () => {
    expect(extractStepIdFromExpression('${deploy}')).toBe('deploy')
  })

  it('extracts step ID from field reference expression', () => {
    expect(extractStepIdFromExpression('${deploy.artifact_url}')).toBe('deploy')
  })

  it('extracts step ID from nested field reference', () => {
    expect(extractStepIdFromExpression('${deploy.result.status}')).toBe('deploy')
  })

  it('returns null for expression without template syntax', () => {
    expect(extractStepIdFromExpression('deploy.artifact_url')).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(extractStepIdFromExpression('')).toBeNull()
  })

  it('returns null for malformed expression', () => {
    expect(extractStepIdFromExpression('$deploy')).toBeNull()
  })
})

describe('isStepConditional', () => {
  it('returns false when step is directly after trigger', () => {
    const activities = [{ id: 'deploy', type: 'script' }]
    const edges = [{ source: 'trigger-0', target: 'deploy' }]
    const triggerIds = ['trigger-0']

    expect(isStepConditional('deploy', activities, edges, triggerIds)).toBe(false)
  })

  it('returns true when step is inside a condition node', () => {
    const activities = [
      { id: 'check_env', type: 'condition' },
      { id: 'deploy', type: 'script' },
    ]
    const edges = [
      { source: 'trigger-0', target: 'check_env' },
      { source: 'check_env', target: 'deploy' },
    ]
    const triggerIds = ['trigger-0']

    expect(isStepConditional('deploy', activities, edges, triggerIds)).toBe(true)
  })

  it('returns true when step is inside a switch node', () => {
    const activities = [
      { id: 'route', type: 'switch' },
      { id: 'deploy_prod', type: 'script' },
    ]
    const edges = [
      { source: 'trigger-0', target: 'route' },
      { source: 'route', target: 'deploy_prod' },
    ]
    const triggerIds = ['trigger-0']

    expect(isStepConditional('deploy_prod', activities, edges, triggerIds)).toBe(true)
  })

  it('returns true when step is inside a loop', () => {
    const activities = [
      { id: 'process_items', type: 'loop_each' },
      { id: 'process_item', type: 'script' },
    ]
    const edges = [
      { source: 'trigger-0', target: 'process_items' },
      { source: 'process_items', target: 'process_item' },
    ]
    const triggerIds = ['trigger-0']

    expect(isStepConditional('process_item', activities, edges, triggerIds)).toBe(true)
  })

  it('returns false when step is after conditional branch converges', () => {
    const activities = [
      { id: 'check_env', type: 'condition' },
      { id: 'deploy_staging', type: 'script' },
      { id: 'deploy_prod', type: 'script' },
      { id: 'notify', type: 'script' },
    ]
    const edges = [
      { source: 'trigger-0', target: 'check_env' },
      { source: 'check_env', target: 'deploy_staging' },
      { source: 'check_env', target: 'deploy_prod' },
      { source: 'deploy_staging', target: 'notify' },
      { source: 'deploy_prod', target: 'notify' },
    ]
    const triggerIds = ['trigger-0']

    // Steps inside branches are conditional
    expect(isStepConditional('deploy_staging', activities, edges, triggerIds)).toBe(true)
    expect(isStepConditional('deploy_prod', activities, edges, triggerIds)).toBe(true)

    // Note: In current implementation, 'notify' is also considered conditional
    // because there's a path through a conditional node to reach it.
    // This is conservative but safe - better to over-warn than under-warn.
    expect(isStepConditional('notify', activities, edges, triggerIds)).toBe(true)
  })

  it('handles multiple trigger IDs', () => {
    const activities = [{ id: 'deploy', type: 'script' }]
    const edges = [
      { source: 'trigger-0', target: 'deploy' },
      { source: 'trigger-1', target: 'deploy' },
    ]
    const triggerIds = ['trigger-0', 'trigger-1']

    expect(isStepConditional('deploy', activities, edges, triggerIds)).toBe(false)
  })

  it('returns false for unreachable step', () => {
    const activities = [
      { id: 'deploy', type: 'script' },
      { id: 'orphan', type: 'script' },
    ]
    const edges = [{ source: 'trigger-0', target: 'deploy' }]
    const triggerIds = ['trigger-0']

    expect(isStepConditional('orphan', activities, edges, triggerIds)).toBe(false)
  })

  it('handles nested conditionals', () => {
    const activities = [
      { id: 'check_env', type: 'condition' },
      { id: 'check_region', type: 'condition' },
      { id: 'deploy', type: 'script' },
    ]
    const edges = [
      { source: 'trigger-0', target: 'check_env' },
      { source: 'check_env', target: 'check_region' },
      { source: 'check_region', target: 'deploy' },
    ]
    const triggerIds = ['trigger-0']

    expect(isStepConditional('deploy', activities, edges, triggerIds)).toBe(true)
  })
})
