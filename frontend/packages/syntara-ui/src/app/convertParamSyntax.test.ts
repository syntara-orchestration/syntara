import { describe, expect, it } from 'vitest'

import { toTanStackPathTemplate } from './convertParamSyntax'

describe('toTanStackPathTemplate', () => {
  it('returns an unchanged path when there are no params', () => {
    expect(toTanStackPathTemplate('/workflows')).toBe('/workflows')
  })

  it('converts a single :param to $param', () => {
    expect(toTanStackPathTemplate('/workflows/:workflowId')).toBe('/workflows/$workflowId')
  })

  it('converts multiple :params', () => {
    expect(toTanStackPathTemplate('/users/:userId/groups/:groupId')).toBe('/users/$userId/groups/$groupId')
  })

  it('strips the trailing ? from an optional param', () => {
    expect(toTanStackPathTemplate('/settings/:tab?')).toBe('/settings/$tab')
  })

  it('handles a param at the very end of the path', () => {
    expect(toTanStackPathTemplate('/:id')).toBe('/$id')
  })

  it('handles a param in the middle of the path', () => {
    expect(toTanStackPathTemplate('/users/:userId/edit')).toBe('/users/$userId/edit')
  })

  it('leaves TanStack $param templates unchanged', () => {
    expect(toTanStackPathTemplate('/users/$userId/edit')).toBe('/users/$userId/edit')
  })
})
