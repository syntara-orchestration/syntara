import { describe, expect, it } from 'vitest'

import { getApprovalPromptFromNode, getApprovalPromptFromRecord } from './approvalPrompt'

describe('getApprovalPromptFromNode', () => {
  it('returns parameters.prompt for v2 approval nodes', () => {
    expect(
      getApprovalPromptFromNode({
        parameters: { prompt: 'Please review this change.' },
      })
    ).toBe('Please review this change.')
  })

  it('falls back to config.prompt for legacy node shapes', () => {
    expect(
      getApprovalPromptFromNode({
        config: { prompt: 'Legacy prompt' },
      })
    ).toBe('Legacy prompt')
  })

  it('prefers parameters.prompt when both shapes exist', () => {
    expect(
      getApprovalPromptFromNode({
        parameters: { prompt: 'From parameters' },
        config: { prompt: 'From config' },
      })
    ).toBe('From parameters')
  })

  it('returns undefined when the node is missing', () => {
    expect(getApprovalPromptFromNode(undefined)).toBeUndefined()
  })

  it('returns undefined when prompt is missing', () => {
    expect(getApprovalPromptFromNode({ parameters: {} })).toBeUndefined()
  })

  it('returns undefined when prompt is empty or whitespace', () => {
    expect(getApprovalPromptFromNode({ parameters: { prompt: '' } })).toBeUndefined()
    expect(getApprovalPromptFromNode({ parameters: { prompt: '   ' } })).toBeUndefined()
  })

  it('returns undefined when prompt is not a string', () => {
    expect(getApprovalPromptFromNode({ parameters: { prompt: 123 } })).toBeUndefined()
    expect(getApprovalPromptFromNode({ config: { prompt: ['nope'] } })).toBeUndefined()
  })

  it('returns undefined when parameters and config are not objects', () => {
    expect(getApprovalPromptFromNode({ parameters: 'invalid', config: null })).toBeUndefined()
  })
})

describe('getApprovalPromptFromRecord', () => {
  it('returns the persisted prompt', () => {
    expect(getApprovalPromptFromRecord({ prompt: 'Please review this change.' })).toBe('Please review this change.')
  })

  it('trims whitespace', () => {
    expect(getApprovalPromptFromRecord({ prompt: '  Please review.  ' })).toBe('Please review.')
  })

  it('returns undefined for missing, blank, or non-string prompts', () => {
    expect(getApprovalPromptFromRecord(undefined)).toBeUndefined()
    expect(getApprovalPromptFromRecord({})).toBeUndefined()
    expect(getApprovalPromptFromRecord({ prompt: null })).toBeUndefined()
    expect(getApprovalPromptFromRecord({ prompt: '' })).toBeUndefined()
    expect(getApprovalPromptFromRecord({ prompt: '   ' })).toBeUndefined()
  })
})
