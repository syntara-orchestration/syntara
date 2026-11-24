import { ActivityTypeEnum, EdgeHandleEnum, TriggerTypeEnum, type Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'

import type { EdgeConnection } from './types/edge'
import {
  WEBMCP_WORKFLOW_NODE_TYPES,
  buildWorkflowDraft,
  cleanText,
  copyParameterObject,
  findSupportedType,
  stripControlCharacters,
  validateWorkflowDraft,
} from './workflowWebMcp'

const emptyWorkflow = {
  id: 'workflow-1',
  name: 'Untitled',
  description: '',
  workflow: { activities: [] },
  triggers: [],
} as unknown as WorkflowDefinition

function build(input: unknown) {
  return buildWorkflowDraft(input, emptyWorkflow, [])
}

function expectBuildFailure(input: unknown, message: string) {
  expect(build(input)).toMatchObject({ ok: false, message })
}

describe('WebMCP input helpers', () => {
  it('strips control and direction characters while retaining normal Unicode', () => {
    expect(stripControlCharacters('Hello\u0000, world\u202e! 🌙')).toBe('Hello, world! 🌙')
  })

  it('cleans and bounds required text', () => {
    expect(cleanText('  name\u0000  ', 'Name', 10)).toBe('name')
    expect(() => cleanText(42, 'Name', 10)).toThrow('Name must be text.')
    expect(() => cleanText('  ', 'Name', 10)).toThrow('Name is required.')
    expect(() => cleanText('too long', 'Name', 3)).toThrow('Name must be 3 characters or fewer.')
  })

  it('accepts and clones JSON parameters without sharing nested objects', () => {
    const parameters = { nested: { enabled: true }, list: [1, 'two', null] }
    const copy = copyParameterObject(parameters, 'parameters')
    expect(copy).toEqual(parameters)
    expect(copy).not.toBe(parameters)
    expect(copy.nested).not.toBe(parameters.nested)
  })

  it('rejects non-object, secret, reserved, cyclic, oversized, and non-JSON parameters', () => {
    expect(() => copyParameterObject([], 'parameters')).toThrow('parameters must be an object.')
    expect(() => copyParameterObject({ access_token: 'value' }, 'parameters')).toThrow(
      'parameters.access_token may contain a secret.'
    )
    expect(() => copyParameterObject(JSON.parse('{"__proto__": {"polluted": true}}'), 'parameters')).toThrow(
      'parameters contains a reserved property.'
    )

    const cyclic: Record<string, unknown> = {}
    cyclic.self = cyclic
    expect(() => copyParameterObject(cyclic, 'parameters')).toThrow('parameters.self must not contain circular values.')
    expect(() => copyParameterObject({ value: Number.NaN }, 'parameters')).toThrow(
      'parameters.value must contain JSON values only.'
    )
    expect(() => copyParameterObject({ values: Array.from({ length: 101 }, () => 1) }, 'parameters')).toThrow(
      'parameters.values has too many items.'
    )
  })

  it('finds only exact supported string values', () => {
    expect(findSupportedType(WEBMCP_WORKFLOW_NODE_TYPES, ActivityTypeEnum.SCRIPT)).toBe(ActivityTypeEnum.SCRIPT)
    expect(findSupportedType(WEBMCP_WORKFLOW_NODE_TYPES, 'unknown')).toBeNull()
    expect(findSupportedType(WEBMCP_WORKFLOW_NODE_TYPES, null)).toBeNull()
  })
})

describe('buildWorkflowDraft', () => {
  const scriptNode = {
    id: 'task-1',
    type: ActivityTypeEnum.SCRIPT,
    name: 'Script',
    parameters: { language: 'python', code: 'print(1)' },
  }

  it('builds a graph draft with a default trigger and default edge handles', () => {
    const result = build({
      name: '  Example  ',
      description: ' Workflow ',
      nodes: [scriptNode],
      edges: [{ source: 'trigger-0', target: 'task-1' }],
    })
    expect(result).toMatchObject({
      ok: true,
      name: 'Example',
      description: 'Workflow',
      workflow: {
        triggers: [{ type: TriggerTypeEnum.MANUAL_TRIGGER, name: 'Manual Trigger', parameters: {} }],
        workflow: { activities: [scriptNode] },
      },
      edges: [
        {
          source: 'trigger-0',
          target: 'task-1',
          sourceHandle: EdgeHandleEnum.SOURCE,
          targetHandle: EdgeHandleEnum.TARGET,
        },
      ],
    })
    if (result.ok) expect(result.edges[0].id).toEqual(expect.any(String))
  })

  it('supports ordered legacy steps and derives their sequential connections', () => {
    const result = build({
      name: 'Linear',
      description: '',
      steps: [
        { type: ActivityTypeEnum.AGENTIC, name: 'First', parameters: { prompt: 'go' } },
        { type: ActivityTypeEnum.APPROVAL, name: 'Second' },
      ],
    })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.edges).toHaveLength(2)
      expect(result.edges[0]).toMatchObject({ source: 'trigger-0', target: result.workflow.workflow.activities[0].id })
      expect(result.edges[1]).toMatchObject({
        source: result.workflow.workflow.activities[0].id,
        target: result.workflow.workflow.activities[1].id,
        sourceHandle: EdgeHandleEnum.SOURCE,
      })
    }
  })

  it('preserves branch-specific source handles and explicit secondary triggers', () => {
    const result = build({
      name: 'Branches',
      description: '',
      triggers: [
        { type: TriggerTypeEnum.MANUAL_TRIGGER, name: 'Manual' },
        { type: TriggerTypeEnum.WEBHOOK_TRIGGER, name: 'Webhook' },
      ],
      nodes: [
        { id: 'condition-1', type: ActivityTypeEnum.CONDITION, name: 'Condition' },
        { id: 'task-yes', type: ActivityTypeEnum.SCRIPT, name: 'Yes' },
        { id: 'task-no', type: ActivityTypeEnum.SCRIPT, name: 'No' },
      ],
      edges: [
        { source: 'trigger-0', target: 'condition-1' },
        { source: 'trigger-1', target: 'condition-1' },
        { source: 'condition-1', target: 'task-yes', source_handle: EdgeHandleEnum.TRUE },
        { source: 'condition-1', target: 'task-no', source_handle: EdgeHandleEnum.FALSE },
      ],
    })
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.edges.map((edge) => edge.sourceHandle)).toEqual(['source', 'source', 'true', 'false'])
  })

  it('rejects a missing or already populated builder', () => {
    expect(buildWorkflowDraft({}, null, [])).toMatchObject({
      ok: false,
      message: 'The workflow builder is still loading. Try again shortly.',
    })
    const populated = { ...emptyWorkflow, workflow: { activities: [scriptNode as Activity] } }
    expect(buildWorkflowDraft({}, populated, [])).toMatchObject({
      ok: false,
      message: 'Draft creation is available on an empty workflow builder.',
    })
    expect(buildWorkflowDraft({}, emptyWorkflow, [{ id: 'edge-1' } as EdgeConnection])).toMatchObject({
      ok: false,
      message: 'Draft creation is available on an empty workflow builder.',
    })
  })

  it('rejects ambiguous formats, malformed names, and unsupported step types', () => {
    expectBuildFailure({}, 'Workflow name must be text.')
    expectBuildFailure({ name: ' ', description: '', steps: [] }, 'Workflow name is required.')
    expectBuildFailure({ name: 'Test', steps: [] }, 'Workflow description must be text.')
    expectBuildFailure(
      { name: 'Test', description: '', steps: [], nodes: [] },
      'Provide either ordered "steps" or graph "nodes" with "edges", not both.'
    )
    expectBuildFailure(
      { name: 'Test', description: '', steps: [{ type: 'switch', name: 'Switch' }] },
      'Step 1 has an unsupported type. Use graph nodes and edges for other node types.'
    )
    expectBuildFailure(
      { name: 'Test', description: '', nodes: [scriptNode] },
      'Graph nodes need explicit "edges" that connect triggers, branches, and steps.'
    )
  })

  it('rejects duplicate IDs, dangerous node IDs, missing graph references, and duplicate edges', () => {
    expectBuildFailure(
      {
        name: 'Test',
        description: '',
        nodes: [scriptNode, scriptNode],
        edges: [{ source: 'trigger-0', target: 'task-1' }],
      },
      'Node ID "task-1" is used more than once.'
    )
    expectBuildFailure(
      {
        name: 'Test',
        description: '',
        nodes: [{ ...scriptNode, id: 'trigger-1' }],
        edges: [{ source: 'trigger-0', target: 'trigger-1' }],
      },
      'Node 1 ID must use letters, numbers, underscores, periods, or hyphens and cannot look like a trigger reference.'
    )
    expectBuildFailure(
      { name: 'Test', description: '', nodes: [scriptNode], edges: [{ source: 'trigger-2', target: 'task-1' }] },
      'Edge 1 refers to missing trigger "trigger-2".'
    )
    expectBuildFailure(
      { name: 'Test', description: '', nodes: [scriptNode], edges: [{ source: 'missing', target: 'task-1' }] },
      'Edge 1 source "missing" does not match a workflow node or trigger reference.'
    )
    expectBuildFailure(
      { name: 'Test', description: '', nodes: [scriptNode], edges: [{ source: 'trigger-0', target: 'missing' }] },
      'Edge 1 target "missing" does not match a workflow node.'
    )
    expectBuildFailure(
      {
        name: 'Test',
        description: '',
        nodes: [scriptNode],
        edges: [
          { source: 'trigger-0', target: 'task-1' },
          { source: 'trigger-0', target: 'task-1' },
        ],
      },
      'The edge from "trigger-0" to "task-1" is duplicated.'
    )
  })

  it('validates handles for triggers, branches, and loop back edges', () => {
    const condition = { id: 'condition-1', type: ActivityTypeEnum.CONDITION, name: 'Condition' }
    expectBuildFailure(
      {
        name: 'Test',
        description: '',
        nodes: [condition, scriptNode],
        edges: [{ source: 'condition-1', target: 'task-1', source_handle: 'source' }],
      },
      'Condition node edges must use the "true" or "false" source_handle.'
    )
    expectBuildFailure(
      {
        name: 'Test',
        description: '',
        nodes: [scriptNode],
        edges: [{ source: 'trigger-0', target: 'task-1', source_handle: 'true' }],
      },
      'Trigger edges must use the default "source" source_handle.'
    )
    expectBuildFailure(
      {
        name: 'Test',
        description: '',
        nodes: [scriptNode],
        edges: [{ source: 'trigger-0', target: 'task-1', target_handle: 'end' }],
      },
      'Edge 1 may use target_handle "end" only when connecting back to a loop node.'
    )
  })

  it('rejects secrets and oversized workflow configuration', () => {
    expectBuildFailure(
      {
        name: 'Test',
        description: '',
        nodes: [{ ...scriptNode, parameters: { password: 'secret' } }],
        edges: [{ source: 'trigger-0', target: 'task-1' }],
      },
      'Node 1 parameters.password may contain a secret. Use a Syntara credential reference instead.'
    )
    expectBuildFailure(
      {
        name: 'Test',
        description: '',
        nodes: [{ ...scriptNode, parameters: { code: 'x'.repeat(50_001) } }],
        edges: [{ source: 'trigger-0', target: 'task-1' }],
      },
      'Workflow node configuration is too large.'
    )
  })
})

describe('validateWorkflowDraft', () => {
  it('returns validation errors and readiness for an empty graph', () => {
    const result = validateWorkflowDraft([], [], [])
    expect(result.readyToRun).toBe(false)
    expect(result.errors.length).toBeGreaterThan(0)
    expect(Array.isArray(result.warnings)).toBe(true)
  })
})
