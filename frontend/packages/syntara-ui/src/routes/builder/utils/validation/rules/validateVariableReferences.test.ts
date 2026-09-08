import type { Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../../../types/edge'
import type { ValidationContext } from '../types'

import { validateVariableReferences } from './validateVariableReferences'

function makeActivity(overrides: Partial<Activity> & { id: string; type: string }): Activity {
  return { parameters: {}, name: overrides.name ?? overrides.id, ...overrides }
}

function makeTriggerWithInputs(fields: string[]): Activity {
  const properties: Record<string, { type: string }> = {}
  for (const f of fields) {
    properties[f] = { type: 'string' }
  }
  return makeActivity({
    id: 'trigger-0',
    type: 'manual',
    parameters: { input_schema: { type: 'object', properties } },
  })
}

describe('validateVariableReferences', () => {
  describe('unknown names (same rule as missing nodes)', () => {
    it.each(['input', 'inputs', 'variables'])(
      'errors on ${%s.*} when no node has that id, even if the field exists on the trigger schema',
      (namespace) => {
        const activities: Activity[] = [
          makeActivity({
            id: 'task-1',
            type: 'script',
            parameters: { code: `echo \${${namespace}.username}` },
          }),
        ]
        const context: ValidationContext = { triggers: [makeTriggerWithInputs(['username'])] }

        const errors = validateVariableReferences(activities, [], context)
        expect(errors).toHaveLength(1)
        expect(errors[0].severity).toBe('error')
        expect(errors[0].nodeId).toBe('task-1')
        expect(errors[0].message).toContain(`node "${namespace}" does not exist`)
        expect(errors[0].message).not.toContain('supported namespace')
      }
    )

    it('errors on a bare ${input} reference when no node is named input', () => {
      const activities: Activity[] = [makeActivity({ id: 'task-1', type: 'script', parameters: { code: '${input}' } })]
      const context: ValidationContext = { triggers: [makeTriggerWithInputs(['foo'])] }

      const errors = validateVariableReferences(activities, [], context)
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toContain('node "input" does not exist')
    })

    it.each(['input', 'inputs', 'variables'])('accepts ${%s.stdout} when a node is actually named %s', (namespace) => {
      const activities: Activity[] = [
        makeActivity({ id: namespace, type: 'script', parameters: { code: 'echo hello' } }),
        makeActivity({ id: 'task-1', type: 'script', parameters: { code: `\${${namespace}.stdout}` } }),
      ]
      const edges: EdgeConnection[] = [{ id: 'e1', source: namespace, target: 'task-1' }]

      expect(validateVariableReferences(activities, edges)).toEqual([])
    })
  })

  describe('node references (AC2)', () => {
    it('returns no warnings when referencing an existing upstream node', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'gather', type: 'script', parameters: { code: 'echo hello' } }),
        makeActivity({ id: 'process', type: 'script', parameters: { code: '${gather.stdout}' } }),
      ]
      const edges: EdgeConnection[] = [{ id: 'e1', source: 'gather', target: 'process' }]

      const warnings = validateVariableReferences(activities, edges)
      expect(warnings).toEqual([])
    })

    it('returns warning when referencing a non-existent node', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'task-1', type: 'script', parameters: { code: '${missing_node.stdout}' } }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings).toHaveLength(1)
      expect(warnings[0].severity).toBe('error')
      expect(warnings[0].nodeId).toBe('task-1')
      expect(warnings[0].message).toContain('missing_node')
      expect(warnings[0].message).toContain('does not exist')
      expect(warnings[0].suggestion).toContain('typos')
    })

    it('returns warning when referencing a node that is not upstream', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'task-a', type: 'script', parameters: { code: 'echo a' } }),
        makeActivity({ id: 'task-b', type: 'script', parameters: { code: '${task-a.stdout}' } }),
      ]
      const edges: EdgeConnection[] = []

      const warnings = validateVariableReferences(activities, edges)
      expect(warnings).toHaveLength(1)
      expect(warnings[0].message).toContain('not upstream')
    })

    it('validates transitive upstream references', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'step-1', type: 'script', parameters: { code: 'echo 1' } }),
        makeActivity({ id: 'step-2', type: 'script', parameters: { code: 'echo 2' } }),
        makeActivity({ id: 'step-3', type: 'script', parameters: { code: '${step-1.output}' } }),
      ]
      const edges: EdgeConnection[] = [
        { id: 'e1', source: 'step-1', target: 'step-2' },
        { id: 'e2', source: 'step-2', target: 'step-3' },
      ]

      const warnings = validateVariableReferences(activities, edges)
      expect(warnings).toEqual([])
    })
  })

  describe('warning format (AC3)', () => {
    it('includes affected node ID in warning', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'my-node', type: 'script', parameters: { code: '${nonexistent.out}' } }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings[0].nodeId).toBe('my-node')
    })

    it('includes the invalid reference in the message', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'task-1', type: 'script', parameters: { code: '${bad_ref.field}' } }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings[0].message).toContain('bad_ref.field')
    })

    it('includes a suggestion in the warning', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'task-1', type: 'script', parameters: { code: '${nowhere.out}' } }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings[0].suggestion).toBeTruthy()
    })

    it('uses activity name in message when available', () => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          name: 'Gather Data',
          type: 'script',
          parameters: { code: '${missing.out}' },
        }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings[0].message).toContain('Gather Data')
    })
  })

  describe('severity (AC4)', () => {
    it('all issues have severity "error"', () => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          type: 'script',
          parameters: { code: '${missing.out} ${input.bad}' },
        }),
      ]
      const context: ValidationContext = { triggers: [makeTriggerWithInputs(['good'])] }

      const warnings = validateVariableReferences(activities, [], context)
      expect(warnings.length).toBeGreaterThan(0)
      for (const w of warnings) {
        expect(w.severity).toBe('error')
      }
    })
  })

  describe('skipped namespaces', () => {
    it.each(['workflow', 'workflow_context'])('does not error for ${%s.*} references', (namespace) => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          type: 'script',
          parameters: { code: `\${${namespace}.some_field}` },
        }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings).toEqual([])
    })
  })

  describe('trigger references', () => {
    it('accepts valid trigger field', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'task-1', type: 'script', parameters: { code: '${trigger.userId}' } }),
      ]
      const context: ValidationContext = { triggers: [makeTriggerWithInputs(['userId'])] }
      expect(validateVariableReferences(activities, [], context)).toEqual([])
    })

    it('errors on invalid trigger field', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'task-1', type: 'script', parameters: { code: '${trigger.missing}' } }),
      ]
      const context: ValidationContext = { triggers: [makeTriggerWithInputs(['userId'])] }
      const errors = validateVariableReferences(activities, [], context)
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toContain('missing')
      expect(errors[0].message).toContain('not a defined trigger field')
      expect(errors[0].suggestion).toContain('userId')
    })

    it('errors on trigger reference when no triggers provided', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'task-1', type: 'script', parameters: { code: '${trigger.anything}' } }),
      ]
      const errors = validateVariableReferences(activities, [])
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toContain('anything')
      expect(errors[0].message).toContain('not a defined trigger field')
    })

    it('collects schema fields from multiple triggers', () => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          type: 'script',
          parameters: { code: '${trigger.fromWebhook}' },
        }),
      ]
      const context: ValidationContext = {
        triggers: [makeTriggerWithInputs(['fromManual']), makeTriggerWithInputs(['fromWebhook'])],
      }

      expect(validateVariableReferences(activities, [], context)).toEqual([])
    })
  })

  describe('edge cases', () => {
    it('handles empty workflow', () => {
      const warnings = validateVariableReferences([], [])
      expect(warnings).toEqual([])
    })

    it('handles activities with no parameters', () => {
      const activities: Activity[] = [makeActivity({ id: 'task-1', type: 'converge' })]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings).toEqual([])
    })

    it('handles activities with non-string parameters', () => {
      const activities: Activity[] = [
        makeActivity({ id: 'task-1', type: 'script', parameters: { timeout: 30, retry: true } }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings).toEqual([])
    })

    it('extracts references from nested parameter objects', () => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          type: 'http_request',
          parameters: {
            url: 'https://example.com',
            headers: { Authorization: 'Bearer ${missing_node.token}' },
          },
        }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings).toHaveLength(1)
      expect(warnings[0].message).toContain('missing_node')
    })

    it('extracts references from parameter arrays', () => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          type: 'script',
          parameters: { args: ['${missing_a.out}', '${missing_b.out}'] },
        }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings).toHaveLength(2)
    })

    it('handles multiple references in a single string', () => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          type: 'script',
          parameters: { code: '${gather.host} on port ${gather.port}' },
        }),
        makeActivity({ id: 'gather', type: 'script', parameters: { code: 'echo hi' } }),
      ]
      const edges: EdgeConnection[] = [{ id: 'e1', source: 'gather', target: 'task-1' }]

      const warnings = validateVariableReferences(activities, edges)
      expect(warnings).toEqual([])
    })

    it('does not produce duplicate warnings for the same node reference', () => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          type: 'script',
          parameters: { code: '${missing.a} and ${missing.b}' },
        }),
      ]

      const warnings = validateVariableReferences(activities, [])
      const nodeRefWarnings = warnings.filter((w) => w.id.startsWith('var-ref-node-'))
      expect(nodeRefWarnings).toHaveLength(1)
    })

    it('does not warn for strings without variable references', () => {
      const activities: Activity[] = [
        makeActivity({
          id: 'task-1',
          type: 'script',
          parameters: { code: 'echo "hello world"', language: 'bash' },
        }),
      ]

      const warnings = validateVariableReferences(activities, [])
      expect(warnings).toEqual([])
    })
  })
})
