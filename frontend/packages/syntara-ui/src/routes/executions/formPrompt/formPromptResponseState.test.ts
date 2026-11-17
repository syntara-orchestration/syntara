import { describe, expect, it } from 'vitest'

import {
  formPromptClosedStatusLabel,
  isFormPromptPastResponseTimeout,
  isFormPromptResponsePending,
} from './formPromptResponseState'

const basePrompt = {
  id: 'fp-1',
  execution_id: 'exec-1',
  project_id: 'proj-1',
  prompt_node_id: 'node',
  name: 'Form',
  status: 'pending' as const,
  form_definition: { fields: [] },
  timeout_at: '2030-01-01T00:00:00.000Z',
}

describe('formPromptResponseState', () => {
  it('treats pending prompt before timeout as open', () => {
    const now = Date.parse('2026-01-01T00:00:00.000Z')
    expect(isFormPromptResponsePending({ ...basePrompt, status: 'pending' }, now)).toBe(true)
  })

  it('closes response window after timeout_at even when status is still pending', () => {
    const now = Date.parse('2030-06-01T00:00:00.000Z')
    expect(isFormPromptResponsePending({ ...basePrompt, status: 'pending' }, now)).toBe(false)
  })

  it('keeps form open when status is expired but timeout_at is still in the future', () => {
    const now = Date.parse('2026-01-01T00:00:00.000Z')
    expect(isFormPromptResponsePending({ ...basePrompt, status: 'expired' }, now)).toBe(true)
  })

  it('labels closed state as expired when past timeout', () => {
    const now = Date.parse('2030-06-01T00:00:00.000Z')
    expect(isFormPromptPastResponseTimeout(basePrompt.timeout_at, now)).toBe(true)
    expect(formPromptClosedStatusLabel({ ...basePrompt, status: 'pending' }, now)).toBe('expired')
  })
})
