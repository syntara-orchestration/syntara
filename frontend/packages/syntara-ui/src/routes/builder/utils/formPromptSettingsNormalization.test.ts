import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../types/edge'

import {
  buildOutgoingPorts,
  formPromptHasFallbackEdge,
  normalizeFormPromptActivityForDefinition,
} from './formPromptSettingsNormalization'

function formActivity(id: string, parameters?: Record<string, unknown>, settings?: Activity['settings']): Activity {
  return {
    id,
    type: ActivityTypeEnum.FORM_PROMPT,
    name: 'Form',
    parameters: { form_definition: { type: 'object' }, ...parameters },
    ...(settings ? { settings } : {}),
  }
}

describe('formPromptSettingsNormalization', () => {
  it('detects fallback edges by sourceHandle', () => {
    const edges: EdgeConnection[] = [{ id: 'e1', source: 'form-1', target: 'next', sourceHandle: 'fallback' }]
    expect(formPromptHasFallbackEdge('form-1', edges)).toBe(true)
    expect(formPromptHasFallbackEdge('form-2', edges)).toBe(false)
  })

  it('does not change settings when stripping fallback_behavior', () => {
    const result = normalizeFormPromptActivityForDefinition(
      formActivity('form-1', { fallback_decision: 'fallback', fallback_behavior: 'fallback' }, { continue_on_failure: false })
    )
    expect(result.settings).toEqual({ continue_on_failure: false })
    expect(result.parameters).toMatchObject({ fallback_decision: 'fallback' })
    expect(result.parameters).not.toHaveProperty('fallback_behavior')
  })

  it('strips fallback_behavior before workflow definition save', () => {
    const result = normalizeFormPromptActivityForDefinition(
      formActivity('form-1', { fallback_decision: 'submit', fallback_behavior: 'fail' })
    )
    expect(result.parameters).toMatchObject({ fallback_decision: 'submit' })
    expect(result.parameters).not.toHaveProperty('fallback_behavior')
  })

  it('buildOutgoingPorts uses resolved source ids', () => {
    const edges: EdgeConnection[] = [
      { id: 'e1', source: 'display-id', target: 'next', sourceHandle: EdgeHandleEnum.FALLBACK },
    ]
    const ports = buildOutgoingPorts(edges, () => 'resolved-form-id')
    expect(ports.get('resolved-form-id')).toEqual(new Set(['fallback']))
  })
})
