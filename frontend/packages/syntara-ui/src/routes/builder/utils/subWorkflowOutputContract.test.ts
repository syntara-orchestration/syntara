import { describe, expect, it } from 'vitest'

import {
  isSimpleOutputSchemaRepresentable,
  outputFieldsFromSchema,
  outputMappingFromFields,
  outputSchemaFromFields,
} from './subWorkflowOutputContract'

describe('SubWorkflow output contract visual representation', () => {
  it('builds nested JSON Schema from dotted Simple mode paths', () => {
    const schema = outputSchemaFromFields([
      {
        path: 'intake.status',
        type: 'string',
        required: true,
        description: 'Current intake status',
        expression: '${process_intake.status}',
      },
    ])

    expect(schema).toEqual({
      type: 'object',
      properties: {
        intake: {
          type: 'object',
          properties: { status: { type: 'string', description: 'Current intake status' } },
          required: ['status'],
        },
      },
      required: ['intake'],
    })
  })

  it('round-trips nested Advanced schemas and mappings through Simple mode', () => {
    const schema = {
      type: 'object',
      properties: {
        intake: {
          type: 'object',
          description: 'Request information',
          properties: {
            status: { type: 'string', description: 'Current status' },
            ticket_id: { type: 'integer' },
          },
          required: ['status'],
        },
      },
      required: ['intake'],
    }
    const mappings = {
      'intake.status': '${process_intake.status}',
      'intake.ticket_id': '${process_intake.ticket_id}',
    }

    const fields = outputFieldsFromSchema(schema, mappings)
    const roundTripSchema = outputSchemaFromFields(fields, schema)

    expect(fields.map((field) => field.path)).toEqual(['intake.status', 'intake.ticket_id'])
    expect(outputMappingFromFields(fields)).toEqual(mappings)
    expect(roundTripSchema).toEqual(schema)
  })

  it('rejects schemas with composition or dynamic properties from Simple mode', () => {
    expect(
      isSimpleOutputSchemaRepresentable({
        allOf: [{ type: 'object', properties: { release: { type: 'string' } } }],
        properties: { release: { type: 'string' } },
      })
    ).toBe(false)
    expect(
      isSimpleOutputSchemaRepresentable({
        type: 'object',
        properties: { metadata: { type: 'object', additionalProperties: { type: 'string' } } },
      })
    ).toBe(false)
  })

  it('rejects mappings to an object when Simple mode only represents its leaf paths', () => {
    const schema = {
      type: 'object',
      properties: {
        release: {
          type: 'object',
          properties: { tag: { type: 'string' } },
        },
      },
    }

    expect(isSimpleOutputSchemaRepresentable(schema, { release: '${build.release}' })).toBe(false)
    expect(isSimpleOutputSchemaRepresentable(schema, { 'release.tag': '${build.tag}' })).toBe(true)

    expect(outputFieldsFromSchema(schema, { release: '${build.release}' })).toEqual([
      {
        path: 'release',
        type: 'object',
        required: false,
        description: '',
        expression: '${build.release}',
      },
    ])
  })
})
