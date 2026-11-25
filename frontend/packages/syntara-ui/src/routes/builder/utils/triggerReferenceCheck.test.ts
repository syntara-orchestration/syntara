import { describe, expect, it } from 'vitest'

import { activitiesReferenceTrigger, hasNonEmptyInputSchema } from './triggerReferenceCheck'

describe('hasNonEmptyInputSchema', () => {
  it('returns false for null/undefined', () => {
    expect(hasNonEmptyInputSchema(null)).toBe(false)
    expect(hasNonEmptyInputSchema(undefined)).toBe(false)
  })

  it('returns false for empty schema', () => {
    expect(hasNonEmptyInputSchema({})).toBe(false)
  })

  it('returns false when properties exists but is empty', () => {
    expect(hasNonEmptyInputSchema({ type: 'object', properties: {} })).toBe(false)
  })

  it('returns true when properties has fields', () => {
    expect(hasNonEmptyInputSchema({ properties: { name: { type: 'string' } } })).toBe(true)
  })

  it('returns true when required has entries', () => {
    expect(hasNonEmptyInputSchema({ required: ['name'] })).toBe(true)
  })

  it('returns false when required is empty array', () => {
    expect(hasNonEmptyInputSchema({ required: [] })).toBe(false)
  })
})

describe('activitiesReferenceTrigger', () => {
  it('returns false when activities have no parameters', () => {
    expect(activitiesReferenceTrigger([{ parameters: undefined }, {}], ['trigger_manual_0'])).toBe(false)
  })

  it('returns false when no activities exist', () => {
    expect(activitiesReferenceTrigger([], ['trigger_manual_0'])).toBe(false)
  })

  it('returns false when parameters have no trigger references', () => {
    const activities = [
      { parameters: { code: 'echo hello' } },
      { parameters: { url: 'https://example.com', method: 'GET' } },
    ]
    expect(activitiesReferenceTrigger(activities, ['trigger_manual_0'])).toBe(false)
  })

  it('detects ${trigger.*} references', () => {
    const activities = [{ parameters: { code: 'echo ${trigger.user_name}' } }]
    expect(activitiesReferenceTrigger(activities, ['trigger_manual_0'])).toBe(true)
  })

  it('detects ${triggerNodeId.*} references', () => {
    const activities = [{ parameters: { url: '${trigger_webhook_0.endpoint}' } }]
    expect(activitiesReferenceTrigger(activities, ['trigger_webhook_0'])).toBe(true)
  })

  it('detects references embedded in longer strings', () => {
    const activities = [{ parameters: { url: 'https://api.github.com/repos/${trigger.owner}/${trigger.repo}' } }]
    expect(activitiesReferenceTrigger(activities, [])).toBe(true)
  })

  it('detects references in nested parameter objects', () => {
    const activities = [
      {
        parameters: {
          extra_vars: {
            app_name: '${trigger.app_name}',
            env: 'production',
          },
        },
      },
    ]
    expect(activitiesReferenceTrigger(activities, [])).toBe(true)
  })

  it('detects references in arrays within parameters', () => {
    const activities = [{ parameters: { args: ['--name', '${trigger.name}', '--verbose'] } }]
    expect(activitiesReferenceTrigger(activities, [])).toBe(true)
  })

  it('ignores non-trigger namespaces', () => {
    const activities = [{ parameters: { code: '${secrets.api_key} ${workflow.name} ${some_node.output}' } }]
    expect(activitiesReferenceTrigger(activities, ['trigger_manual_0'])).toBe(false)
  })

  it('returns true on the first match without scanning all activities', () => {
    const activities = [{ parameters: { code: '${trigger.field}' } }, { parameters: { code: '${trigger.other}' } }]
    expect(activitiesReferenceTrigger(activities, [])).toBe(true)
  })

  it('handles multiple trigger node IDs', () => {
    const activities = [{ parameters: { value: '${trigger_eda_0.event}' } }]
    expect(activitiesReferenceTrigger(activities, ['trigger_manual_0', 'trigger_eda_0'])).toBe(true)
  })

  it('does not match partial namespace names', () => {
    const activities = [{ parameters: { code: '${triggering.something}' } }]
    expect(activitiesReferenceTrigger(activities, [])).toBe(false)
  })
})
