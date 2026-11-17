import type { OutputFieldDef } from '@syntara/contracts'
import { describe, expect, it, vi } from 'vitest'

import { buildMockJsonSkeleton, parseJsonObject } from './mockDataUtils'

const mockGetNodeOutputSchema = vi.fn<(nodeType: string) => OutputFieldDef[] | null>()

vi.mock('@syntara/contracts', () => ({
  getNodeOutputSchema: (nodeType: string) => mockGetNodeOutputSchema(nodeType),
}))

describe('buildMockJsonSkeleton', () => {
  it('returns empty object when both nodeType and schemaFields are null', () => {
    expect(buildMockJsonSkeleton(null, null)).toBe('{}')
  })

  it('returns empty object when nodeType has no schema and schemaFields is null', () => {
    mockGetNodeOutputSchema.mockReturnValue(null)
    expect(buildMockJsonSkeleton('unknown-type', null)).toBe('{}')
  })

  it('builds JSON from node type output schema', () => {
    mockGetNodeOutputSchema.mockReturnValue([
      { name: 'hostname', type: 'string', description: 'Host name' },
      { name: 'status', type: 'string', description: 'Status code' },
    ])

    const result = buildMockJsonSkeleton('script', null)
    const parsed: unknown = JSON.parse(result)

    expect(parsed).toEqual({
      hostname: '',
      status: '',
    })
  })

  it('falls back to provided schemaFields when nodeType is null', () => {
    const schemaFields: OutputFieldDef[] = [
      { name: 'result', type: 'string', description: 'Result' },
      { name: 'count', type: 'number', description: 'Count' },
    ]

    const result = buildMockJsonSkeleton(null, schemaFields)
    const parsed: unknown = JSON.parse(result)

    expect(parsed).toEqual({
      result: '',
      count: '',
    })
  })

  it('uses provided schemaFields over node type schema when both are present', () => {
    mockGetNodeOutputSchema.mockReturnValue([{ name: 'stdout', type: 'string', description: 'Output' }])

    const schemaFields: OutputFieldDef[] = [{ name: 'fallback', type: 'string', description: 'Fallback' }]

    const result = buildMockJsonSkeleton('script', schemaFields)
    const parsed: unknown = JSON.parse(result)

    expect(parsed).toEqual({ fallback: '' })
  })

  it('handles empty schema array', () => {
    mockGetNodeOutputSchema.mockReturnValue([])
    expect(buildMockJsonSkeleton('script', null)).toBe('{}')
  })

  it('handles schema with multiple field types', () => {
    const schemaFields: OutputFieldDef[] = [
      { name: 'str_field', type: 'string', description: 'String' },
      { name: 'num_field', type: 'number', description: 'Number' },
      { name: 'bool_field', type: 'boolean', description: 'Boolean' },
      { name: 'obj_field', type: 'object', description: 'Object' },
      { name: 'arr_field', type: 'array', description: 'Array' },
      { name: 'unk_field', type: 'unknown', description: 'Unknown' },
    ]

    const result = buildMockJsonSkeleton(null, schemaFields)
    const parsed: unknown = JSON.parse(result)

    expect(parsed).toEqual({
      str_field: '',
      num_field: '',
      bool_field: '',
      obj_field: '',
      arr_field: '',
      unk_field: '',
    })
  })

  it('formats JSON with indentation', () => {
    const schemaFields: OutputFieldDef[] = [
      { name: 'a', type: 'string', description: 'A' },
      { name: 'b', type: 'string', description: 'B' },
    ]

    const result = buildMockJsonSkeleton(null, schemaFields)

    expect(result).toContain('\n')
    expect(result).toContain('  "a"')
    expect(result).toContain('  "b"')
  })
})

describe('parseJsonObject', () => {
  it('parses valid object JSON', () => {
    const result = parseJsonObject('{"key": "value", "count": 42}')

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data).toEqual({ key: 'value', count: 42 })
    }
  })

  it('parses empty object', () => {
    const result = parseJsonObject('{}')

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data).toEqual({})
    }
  })

  it('rejects array JSON', () => {
    const result = parseJsonObject('[1, 2, 3]')

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error).toBe('Mock data must be a JSON object')
    }
  })

  it('rejects null', () => {
    const result = parseJsonObject('null')

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error).toBe('Mock data must be a JSON object')
    }
  })

  it('rejects string primitive', () => {
    const result = parseJsonObject('"hello"')

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error).toBe('Mock data must be a JSON object')
    }
  })

  it('rejects number primitive', () => {
    const result = parseJsonObject('42')

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error).toBe('Mock data must be a JSON object')
    }
  })

  it('rejects boolean primitive', () => {
    const result = parseJsonObject('true')

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error).toBe('Mock data must be a JSON object')
    }
  })

  it('returns parse error for invalid JSON', () => {
    const result = parseJsonObject('{ invalid json }')

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error).toBeDefined()
      expect(result.error.length).toBeGreaterThan(0)
    }
  })

  it('returns parse error for incomplete JSON', () => {
    const result = parseJsonObject('{"key": ')

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error).toBeDefined()
    }
  })

  it('parses object with nested structures', () => {
    const result = parseJsonObject('{"nested": {"key": "value"}, "arr": [1, 2]}')

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data).toEqual({
        nested: { key: 'value' },
        arr: [1, 2],
      })
    }
  })
})
