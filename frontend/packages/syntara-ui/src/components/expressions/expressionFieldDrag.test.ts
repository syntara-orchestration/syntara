import { describe, expect, it } from 'vitest'

import { DRAG_TYPE_CONTEXT, DRAG_TYPE_FIELD, isDragData } from './expressionFieldDrag'

describe('isDragData', () => {
  it('returns false for non-object values', () => {
    expect(isDragData(null)).toBe(false)
    expect(isDragData(undefined)).toBe(false)
    expect(isDragData('field')).toBe(false)
  })

  it('returns true for valid field drag data', () => {
    expect(
      isDragData({
        type: DRAG_TYPE_FIELD,
        nodeId: 'schedule_trigger',
        fieldPath: ['Day of the month'],
      })
    ).toBe(true)
  })

  it('returns true for valid context drag data', () => {
    expect(
      isDragData({
        type: DRAG_TYPE_CONTEXT,
        contextPath: '$now',
      })
    ).toBe(true)
  })

  it('returns false when field drag data is missing required properties', () => {
    expect(isDragData({ type: DRAG_TYPE_FIELD, nodeId: 'node-1' })).toBe(false)
    expect(isDragData({ type: DRAG_TYPE_FIELD, fieldPath: ['value'] })).toBe(false)
    expect(isDragData({ type: DRAG_TYPE_FIELD, nodeId: 1, fieldPath: ['value'] })).toBe(false)
  })

  it('returns false when context drag data is missing contextPath', () => {
    expect(isDragData({ type: DRAG_TYPE_CONTEXT })).toBe(false)
    expect(isDragData({ type: DRAG_TYPE_CONTEXT, contextPath: 123 })).toBe(false)
  })

  it('returns false when field drag data has invalid fieldPath segments', () => {
    expect(
      isDragData({
        type: DRAG_TYPE_FIELD,
        nodeId: 'node-1',
        fieldPath: ['valid', ''],
      })
    ).toBe(false)
    expect(
      isDragData({
        type: DRAG_TYPE_FIELD,
        nodeId: '',
        fieldPath: ['value'],
      })
    ).toBe(false)
  })

  it('returns false when context drag data has an empty contextPath', () => {
    expect(isDragData({ type: DRAG_TYPE_CONTEXT, contextPath: '' })).toBe(false)
  })

  it('returns false for unknown drag types', () => {
    expect(isDragData({ type: 'unknown', nodeId: 'node-1', fieldPath: ['value'] })).toBe(false)
  })
})
