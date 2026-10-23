import { describe, expect, it } from 'vitest'

import {
  createEmptyField,
  fieldsToJsonSchema,
  generateSampleBody,
  jsonSchemaToFields,
  type SimpleField,
} from './simpleSchemaUtils'

type JsonSchema = {
  $schema?: string
  type?: string
  properties?: Record<string, { type: string }>
  required?: string[]
  additionalProperties?: boolean
}

describe('simpleSchemaUtils', () => {
  describe('createEmptyField', () => {
    it('returns a field with default values', () => {
      const field = createEmptyField()
      expect(field.id).toBeTruthy()
      expect(field.name).toBe('')
      expect(field.type).toBe('string')
      expect(field.required).toBe(false)
    })

    it('generates unique ids', () => {
      const a = createEmptyField()
      const b = createEmptyField()
      expect(a.id).not.toBe(b.id)
    })
  })

  describe('fieldsToJsonSchema', () => {
    it('produces a valid JSON schema from fields', () => {
      const fields: SimpleField[] = [
        { id: '1', name: 'event', type: 'string', required: true },
        { id: '2', name: 'count', type: 'integer', required: false },
      ]
      const result = JSON.parse(fieldsToJsonSchema(fields, true)) as JsonSchema
      expect(result).toEqual({
        $schema: 'http://json-schema.org/draft-07/schema#',
        type: 'object',
        properties: {
          event: { type: 'string' },
          count: { type: 'integer' },
        },
        required: ['event'],
        additionalProperties: true,
      })
    })

    it('omits required array when no fields are required', () => {
      const fields: SimpleField[] = [{ id: '1', name: 'name', type: 'string', required: false }]
      const result = JSON.parse(fieldsToJsonSchema(fields, false)) as JsonSchema
      expect(result.required).toBeUndefined()
      expect(result.additionalProperties).toBe(false)
    })

    it('skips fields with empty names', () => {
      const fields: SimpleField[] = [
        { id: '1', name: '', type: 'string', required: true },
        { id: '2', name: 'valid', type: 'number', required: false },
      ]
      const result = JSON.parse(fieldsToJsonSchema(fields, true)) as JsonSchema
      expect(Object.keys(result.properties ?? {})).toEqual(['valid'])
      expect(result.required).toBeUndefined()
    })

    it('produces valid JSON from empty fields', () => {
      const result = JSON.parse(fieldsToJsonSchema([], true)) as JsonSchema
      expect(result.properties).toEqual({})
      expect(result.required).toBeUndefined()
    })

    it('trims field names', () => {
      const fields: SimpleField[] = [{ id: '1', name: '  event  ', type: 'string', required: true }]
      const result = JSON.parse(fieldsToJsonSchema(fields, true)) as JsonSchema
      expect(result.properties).toHaveProperty('event')
      expect(result.required).toEqual(['event'])
    })
  })

  describe('jsonSchemaToFields', () => {
    it('parses a simple schema into fields', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: {
          event: { type: 'string' },
          count: { type: 'integer' },
        },
        required: ['event'],
        additionalProperties: false,
      })
      const result = jsonSchemaToFields(schema)
      expect(result.isSimpleSchema).toBe(true)
      expect(result.additionalProperties).toBe(false)
      expect(result.fields).toHaveLength(2)
      expect(result.fields[0].name).toBe('event')
      expect(result.fields[0].type).toBe('string')
      expect(result.fields[0].required).toBe(true)
      expect(result.fields[1].name).toBe('count')
      expect(result.fields[1].type).toBe('integer')
      expect(result.fields[1].required).toBe(false)
    })

    it('returns empty fields for empty string', () => {
      const result = jsonSchemaToFields('')
      expect(result.isSimpleSchema).toBe(true)
      expect(result.fields).toEqual([])
      expect(result.additionalProperties).toBe(true)
    })

    it('returns empty fields for undefined', () => {
      const result = jsonSchemaToFields(undefined)
      expect(result.isSimpleSchema).toBe(true)
      expect(result.fields).toEqual([])
    })

    it('defaults additionalProperties to true when omitted', () => {
      const schema = JSON.stringify({ type: 'object', properties: {} })
      const result = jsonSchemaToFields(schema)
      expect(result.additionalProperties).toBe(true)
    })

    it('detects invalid JSON as not simple', () => {
      const result = jsonSchemaToFields('{bad json}')
      expect(result.isSimpleSchema).toBe(false)
    })

    it('detects non-object type as not simple', () => {
      const result = jsonSchemaToFields(JSON.stringify({ type: 'array', items: { type: 'string' } }))
      expect(result.isSimpleSchema).toBe(false)
    })

    it('detects oneOf as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        oneOf: [{ properties: { a: { type: 'string' } } }],
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('detects nested object properties as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { nested: { type: 'object', properties: { inner: { type: 'string' } } } },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('detects array properties as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { list: { type: 'array', items: { type: 'string' } } },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('detects enum properties as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { status: { type: 'string', enum: ['active', 'inactive'] } },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('detects pattern properties as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { name: { type: 'string', pattern: '^[a-z]+$' } },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('detects $ref as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        $ref: '#/definitions/Foo',
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('detects property with $ref as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { item: { $ref: '#/definitions/Item' } },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('detects non-object property value (array) as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { list: [1, 2, 3] },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('detects null property value as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { bad: null },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('returns not simple for non-object JSON (number)', () => {
      expect(jsonSchemaToFields('42').isSimpleSchema).toBe(false)
    })

    it('detects unsupported string type as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { custom: { type: 'custom_type' } },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
      expect(jsonSchemaToFields(schema).reason).toBe('complex_schema')
    })

    it('detects array-typed property as not simple', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { tags: { type: 'array' } },
      })
      expect(jsonSchemaToFields(schema).isSimpleSchema).toBe(false)
    })

    it('falls back to string type when property type is non-string', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { weird: { type: 123 } },
      })
      const result = jsonSchemaToFields(schema)
      expect(result.isSimpleSchema).toBe(true)
      expect(result.fields[0].type).toBe('string')
    })

    it('handles schema with $schema field', () => {
      const schema = JSON.stringify({
        $schema: 'http://json-schema.org/draft-07/schema#',
        type: 'object',
        properties: { name: { type: 'string' } },
        additionalProperties: true,
      })
      const result = jsonSchemaToFields(schema)
      expect(result.isSimpleSchema).toBe(true)
      expect(result.fields).toHaveLength(1)
    })
  })

  describe('round-trip', () => {
    it('preserves fields through fieldsToJsonSchema -> jsonSchemaToFields', () => {
      const original: SimpleField[] = [
        { id: '1', name: 'event', type: 'string', required: true },
        { id: '2', name: 'priority', type: 'integer', required: false },
        { id: '3', name: 'active', type: 'boolean', required: true },
      ]

      const json = fieldsToJsonSchema(original, false)
      const parsed = jsonSchemaToFields(json)

      expect(parsed.isSimpleSchema).toBe(true)
      expect(parsed.additionalProperties).toBe(false)
      expect(parsed.fields).toHaveLength(3)

      for (let i = 0; i < original.length; i++) {
        expect(parsed.fields[i].name).toBe(original[i].name)
        expect(parsed.fields[i].type).toBe(original[i].type)
        expect(parsed.fields[i].required).toBe(original[i].required)
      }
    })

    it('preserves empty schema through round-trip', () => {
      const json = fieldsToJsonSchema([], true)
      const parsed = jsonSchemaToFields(json)
      expect(parsed.isSimpleSchema).toBe(true)
      expect(parsed.fields).toHaveLength(0)
      expect(parsed.additionalProperties).toBe(true)
    })
  })

  describe('generateSampleBody', () => {
    it('generates sample values from schema properties', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: {
          event: { type: 'string' },
          count: { type: 'integer' },
          ratio: { type: 'number' },
          active: { type: 'boolean' },
        },
      })
      const result = JSON.parse(generateSampleBody(schema)) as Record<string, unknown>
      expect(result).toEqual({ event: 'example', count: 0, ratio: 0, active: true })
    })

    it('returns {} for empty schema', () => {
      expect(generateSampleBody('')).toBe('{}')
      expect(generateSampleBody(undefined)).toBe('{}')
    })

    it('returns {} for schema with no properties', () => {
      const schema = JSON.stringify({ type: 'object', properties: {} })
      expect(generateSampleBody(schema)).toBe('{}')
    })

    it('returns {} for invalid JSON', () => {
      expect(generateSampleBody('{bad}')).toBe('{}')
    })

    it('returns {} for non-object schema', () => {
      expect(generateSampleBody(JSON.stringify({ type: 'array' }))).toBe('{}')
    })

    it('uses empty object for object type properties', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { data: { type: 'object' } },
      })
      const result = JSON.parse(generateSampleBody(schema)) as Record<string, unknown>
      expect(result).toEqual({ data: {} })
    })

    it('uses empty array for array type properties', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { items: { type: 'array' } },
      })
      const result = JSON.parse(generateSampleBody(schema)) as Record<string, unknown>
      expect(result).toEqual({ items: [] })
    })

    it('uses null for truly unknown property types', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { x: { type: 'custom_unknown' } },
      })
      const result = JSON.parse(generateSampleBody(schema)) as Record<string, unknown>
      expect(result).toEqual({ x: null })
    })

    it('skips non-object property entries', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { bad: 'not an object', good: { type: 'string' } },
      })
      const result = JSON.parse(generateSampleBody(schema)) as Record<string, unknown>
      expect(result).toEqual({ good: 'example' })
    })

    it('returns {} for non-object JSON (array)', () => {
      expect(generateSampleBody('[1, 2, 3]')).toBe('{}')
    })

    it('uses null for properties with no type field', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: { mystery: {} },
      })
      const result = JSON.parse(generateSampleBody(schema)) as Record<string, unknown>
      expect(result).toEqual({ mystery: null })
    })

    it('generates correct sample for mixed types including array and object', () => {
      const schema = JSON.stringify({
        type: 'object',
        properties: {
          action: { type: 'string' },
          items: { type: 'array' },
          priority: { type: 'integer' },
          metadata: { type: 'object' },
        },
      })
      const result = JSON.parse(generateSampleBody(schema)) as Record<string, unknown>
      expect(result).toEqual({ action: 'example', items: [], priority: 0, metadata: {} })
    })

    it('updates when schema changes via fieldsToJsonSchema', () => {
      const fields: SimpleField[] = [
        { id: '1', name: 'event', type: 'string', required: true },
        { id: '2', name: 'priority', type: 'integer', required: false },
      ]
      const schema = fieldsToJsonSchema(fields, true)
      const body = JSON.parse(generateSampleBody(schema)) as Record<string, unknown>
      expect(body).toEqual({ event: 'example', priority: 0 })
    })
  })
})
