import { ActivityTypeEnum, EdgeHandleEnum } from '@syntara/contracts'
import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from './types/edge'
import { convertV2Definition, parseNodePositions } from './utils/processExistingWorkflow'
import { buildWorkflowDefinition } from './utils/workflowDefinitionBuilder'

function makeActivity(overrides: Partial<Activity> & { id: string; type: string }): Activity {
  return { name: overrides.id, parameters: {}, ...overrides }
}

function makeEdge(source: string, target: string, sourceHandle?: string, targetHandle?: string): EdgeConnection {
  return {
    id: `${source}-${target}`,
    source,
    target,
    sourceHandle: sourceHandle ?? EdgeHandleEnum.SOURCE,
    targetHandle: targetHandle ?? 'target',
  }
}

function roundTrip(
  activities: Activity[],
  triggers: Activity[],
  edges: EdgeConnection[],
  name = 'round-trip-test',
  description = ''
) {
  const v2Def = buildWorkflowDefinition(name, description, activities, triggers, { edges })

  const {
    flattenedActivities,
    edges: loadedEdges,
    triggers: loadedTriggers,
  } = convertV2Definition(v2Def.nodes, v2Def.edges, v2Def.triggers)

  const rebuilt = buildWorkflowDefinition(name, description, flattenedActivities, loadedTriggers, {
    edges: loadedEdges,
  })

  return { original: v2Def, rebuilt }
}

describe('V2 Workflow Definition Round-Trip', () => {
  describe('workflow structure preserved through save → load → save cycle', () => {
    it('preserves a simple sequential workflow', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({
          id: 'script_1',
          type: ActivityTypeEnum.SCRIPT,
          parameters: { language: 'python', code: 'print("hello")' },
        }),
        makeActivity({
          id: 'script_2',
          type: ActivityTypeEnum.SCRIPT,
          parameters: { language: 'bash', code: 'echo done' },
        }),
      ]
      const edges = [makeEdge('trigger-0', 'script_1'), makeEdge('script_1', 'script_2')]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      expect(rebuilt.schema_version).toBe('2.0.0')
      expect(rebuilt.nodes).toHaveLength(original.nodes.length)
      expect(rebuilt.edges).toHaveLength(original.edges.length)
      expect(rebuilt.triggers).toHaveLength(original.triggers.length)
    })

    it('preserves node count and types across round-trip', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({ id: 'script_node', type: ActivityTypeEnum.SCRIPT }),
        makeActivity({ id: 'http_node', type: ActivityTypeEnum.HTTP_REQUEST }),
        makeActivity({ id: 'condition_node', type: ActivityTypeEnum.CONDITION }),
      ]
      const edges = [
        makeEdge('trigger-0', 'script_node'),
        makeEdge('script_node', 'http_node'),
        makeEdge('http_node', 'condition_node'),
      ]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      const originalTypes = original.nodes.map((n) => n.type).sort()
      const rebuiltTypes = rebuilt.nodes.map((n) => n.type).sort()
      expect(rebuiltTypes).toEqual(originalTypes)
    })
  })

  describe('edge attributes preserved (from_port, to_port)', () => {
    it('preserves condition branch edges (true/false ports)', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({ id: 'cond', type: ActivityTypeEnum.CONDITION, parameters: { condition: 'true' } }),
        makeActivity({ id: 'true_branch', type: ActivityTypeEnum.SCRIPT }),
        makeActivity({ id: 'false_branch', type: ActivityTypeEnum.SCRIPT }),
      ]
      const edges = [
        makeEdge('trigger-0', 'cond'),
        makeEdge('cond', 'true_branch', EdgeHandleEnum.TRUE),
        makeEdge('cond', 'false_branch', EdgeHandleEnum.FALSE),
      ]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      const originalCondEdges = original.edges.filter((e) => e.from === 'cond')
      const rebuiltCondEdges = rebuilt.edges.filter((e) => e.from === 'cond')

      expect(rebuiltCondEdges).toHaveLength(originalCondEdges.length)

      const trueEdge = rebuiltCondEdges.find((e) => e.from_port === 'true')
      const falseEdge = rebuiltCondEdges.find((e) => e.from_port === 'false')
      expect(trueEdge).toBeDefined()
      expect(falseEdge).toBeDefined()
      expect(trueEdge!.to).toBe('true_branch')
      expect(falseEdge!.to).toBe('false_branch')
    })

    it('preserves loop edges (iterate/complete ports)', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({
          id: 'loop_node',
          type: ActivityTypeEnum.LOOP,
          parameters: { loop_type: 'for_each', items: '${trigger.items}' },
        }),
        makeActivity({ id: 'loop_body', type: ActivityTypeEnum.SCRIPT }),
        makeActivity({ id: 'after_loop', type: ActivityTypeEnum.SCRIPT }),
      ]
      const edges = [
        makeEdge('trigger-0', 'loop_node'),
        makeEdge('loop_node', 'loop_body', EdgeHandleEnum.LOOP),
        makeEdge('loop_node', 'after_loop', EdgeHandleEnum.DONE),
      ]

      const { rebuilt } = roundTrip(activities, triggers, edges)

      const rebuiltLoopEdges = rebuilt.edges.filter((e) => e.from === 'loop_node')
      expect(rebuiltLoopEdges).toHaveLength(2)

      const iterateEdge = rebuiltLoopEdges.find((e) => e.from_port === 'iterate')
      const completeEdge = rebuiltLoopEdges.find((e) => e.from_port === 'complete')
      expect(iterateEdge).toBeDefined()
      expect(completeEdge).toBeDefined()
      expect(iterateEdge!.to).toBe('loop_body')
      expect(completeEdge!.to).toBe('after_loop')
    })

    it('preserves approval edges (approved/rejected ports)', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({ id: 'approval_node', type: ActivityTypeEnum.APPROVAL }),
        makeActivity({ id: 'approved_action', type: ActivityTypeEnum.SCRIPT }),
        makeActivity({ id: 'rejected_action', type: ActivityTypeEnum.SCRIPT }),
      ]
      const edges = [
        makeEdge('trigger-0', 'approval_node'),
        makeEdge('approval_node', 'approved_action', EdgeHandleEnum.APPROVED),
        makeEdge('approval_node', 'rejected_action', EdgeHandleEnum.REJECTED),
      ]

      const { rebuilt } = roundTrip(activities, triggers, edges)

      const rebuiltApprovalEdges = rebuilt.edges.filter((e) => e.from === 'approval_node')
      expect(rebuiltApprovalEdges).toHaveLength(2)

      expect(rebuiltApprovalEdges.find((e) => e.from_port === 'approved')).toBeDefined()
      expect(rebuiltApprovalEdges.find((e) => e.from_port === 'rejected')).toBeDefined()
    })

    it('preserves switch case edges', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({
          id: 'switch_node',
          type: ActivityTypeEnum.SWITCH,
          parameters: {
            cases: [
              { port: 'case_0', label: 'Case A', condition: 'x == 1' },
              { port: 'case_1', label: 'Case B', condition: 'x == 2' },
            ],
          },
        }),
        makeActivity({ id: 'case_a_action', type: ActivityTypeEnum.SCRIPT }),
        makeActivity({ id: 'case_b_action', type: ActivityTypeEnum.SCRIPT }),
        makeActivity({ id: 'default_action', type: ActivityTypeEnum.SCRIPT }),
      ]
      const edges = [
        makeEdge('trigger-0', 'switch_node'),
        makeEdge('switch_node', 'case_a_action', 'case_0'),
        makeEdge('switch_node', 'case_b_action', 'case_1'),
        makeEdge('switch_node', 'default_action', EdgeHandleEnum.DEFAULT),
      ]

      const { rebuilt } = roundTrip(activities, triggers, edges)

      const rebuiltSwitchEdges = rebuilt.edges.filter((e) => e.from === 'switch_node')
      expect(rebuiltSwitchEdges).toHaveLength(3)
      expect(rebuiltSwitchEdges.find((e) => e.from_port === 'case_0')).toBeDefined()
      expect(rebuiltSwitchEdges.find((e) => e.from_port === 'case_1')).toBeDefined()
      expect(rebuiltSwitchEdges.find((e) => e.from_port === 'default')).toBeDefined()
    })
  })

  describe('trigger IDs preserved through round-trip', () => {
    it('preserves manual trigger ID', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [makeActivity({ id: 'script_1', type: ActivityTypeEnum.SCRIPT })]
      const edges = [makeEdge('trigger-0', 'script_1')]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      expect(rebuilt.triggers[0].id).toBe(original.triggers[0].id)
      expect(rebuilt.triggers[0].type).toBe('manual_trigger')
    })

    it('preserves multiple trigger IDs', () => {
      const triggers = [
        makeActivity({ id: 'trigger_manual', type: 'manual_trigger' }),
        makeActivity({ id: 'trigger_webhook', type: 'webhook_trigger', parameters: { path: '/test' } }),
      ]
      const activities = [makeActivity({ id: 'script_1', type: ActivityTypeEnum.SCRIPT })]
      const edges = [makeEdge('trigger-0', 'script_1'), makeEdge('trigger-1', 'script_1')]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      expect(rebuilt.triggers).toHaveLength(2)
      for (let i = 0; i < original.triggers.length; i++) {
        expect(rebuilt.triggers[i].id).toBe(original.triggers[i].id)
        expect(rebuilt.triggers[i].type).toBe(original.triggers[i].type)
      }
    })
  })

  describe('node configs and outputs preserved', () => {
    it('preserves script node parameters', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({
          id: 'script_1',
          type: ActivityTypeEnum.SCRIPT,
          parameters: { language: 'python', code: 'import json\nprint(json.dumps({"result": 42}))' },
        }),
      ]
      const edges = [makeEdge('trigger-0', 'script_1')]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      const originalNode = original.nodes.find((n) => n.id === 'script_1')!
      const rebuiltNode = rebuilt.nodes.find((n) => n.id === 'script_1')!
      expect(rebuiltNode.parameters).toEqual(originalNode.parameters)
    })

    it('preserves HTTP request node parameters', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({
          id: 'http_1',
          type: ActivityTypeEnum.HTTP_REQUEST,
          parameters: {
            method: 'POST',
            url: 'https://api.example.com/data',
            headers: { 'Content-Type': 'application/json' },
          },
        }),
      ]
      const edges = [makeEdge('trigger-0', 'http_1')]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      expect(rebuilt.nodes[0].parameters).toEqual(original.nodes[0].parameters)
    })

    it('preserves node outputs through round-trip', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({
          id: 'script_1',
          type: ActivityTypeEnum.SCRIPT,
          parameters: { language: 'python', code: 'print("hello")' },
          outputs: { result: '$.stdout' },
        }),
      ]
      const edges = [makeEdge('trigger-0', 'script_1')]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      expect(rebuilt.nodes[0].outputs).toEqual(original.nodes[0].outputs)
    })

    it('preserves node settings through round-trip', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({
          id: 'http_1',
          type: ActivityTypeEnum.HTTP_REQUEST,
          parameters: { method: 'GET', url: 'https://api.example.com' },
          settings: {
            timeout: 60,
            continue_on_failure: true,
            retry_policy: { max_attempts: 3, backoff: 'exponential' },
          },
        } as Partial<Activity> & { id: string; type: string }),
      ]
      const edges = [makeEdge('trigger-0', 'http_1')]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      expect(rebuilt.nodes[0].settings).toEqual(original.nodes[0].settings)
    })

    it('preserves trigger parameters through round-trip', () => {
      const triggers = [
        makeActivity({
          id: 'trigger_webhook',
          type: 'webhook_trigger',
          parameters: { path: '/my-webhook', secret: 'test-secret' },
        }),
      ]
      const activities = [makeActivity({ id: 'script_1', type: ActivityTypeEnum.SCRIPT })]
      const edges = [makeEdge('trigger-0', 'script_1')]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      expect(rebuilt.triggers[0].parameters).toEqual(original.triggers[0].parameters)
    })

    it('preserves converge node parameters', () => {
      const triggers = [makeActivity({ id: 'trigger_manual', type: 'manual_trigger' })]
      const activities = [
        makeActivity({ id: 'branch_a', type: ActivityTypeEnum.SCRIPT }),
        makeActivity({ id: 'branch_b', type: ActivityTypeEnum.SCRIPT }),
        makeActivity({
          id: 'converge_node',
          type: ActivityTypeEnum.CONVERGE,
          parameters: { strategy: 'all', timeout_seconds: 300 },
        }),
      ]
      const edges = [
        makeEdge('trigger-0', 'branch_a'),
        makeEdge('trigger-0', 'branch_b'),
        makeEdge('branch_a', 'converge_node'),
        makeEdge('branch_b', 'converge_node'),
      ]

      const { original, rebuilt } = roundTrip(activities, triggers, edges)

      const originalConverge = original.nodes.find((n) => n.id === 'converge_node')!
      const rebuiltConverge = rebuilt.nodes.find((n) => n.id === 'converge_node')!
      expect(rebuiltConverge.parameters).toEqual(originalConverge.parameters)
    })
  })

  describe('node positions preserved through round-trip', () => {
    it('parses valid node positions', () => {
      const rawNodes = [
        { id: 'node_1', position: { x: 100, y: 200 } },
        { id: 'node_2', position: { x: -50, y: 300 } },
      ]

      const positions = parseNodePositions(rawNodes)
      expect(positions['node_1']).toEqual({ x: 100, y: 200 })
      expect(positions['node_2']).toEqual({ x: -50, y: 300 })
    })

    it('rejects invalid positions', () => {
      const rawNodes = [
        { id: 'good', position: { x: 100, y: 200 } },
        { id: 'no_pos' },
        { id: 'nan', position: { x: Number.NaN, y: 200 } },
        { id: 'too_big', position: { x: 2_000_000, y: 200 } },
      ]

      const positions = parseNodePositions(rawNodes)
      expect(positions['good']).toEqual({ x: 100, y: 200 })
      expect(positions['no_pos']).toBeUndefined()
      expect(positions['nan']).toBeUndefined()
      expect(positions['too_big']).toBeUndefined()
    })
  })
})
