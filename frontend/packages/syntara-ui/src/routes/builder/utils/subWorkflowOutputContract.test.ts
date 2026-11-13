import { describe, expect, it } from 'vitest'

import { outputFieldsFromSchema, outputMappingFromFields, outputSchemaFromFields } from './subWorkflowOutputContract'

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
})
