import { describe, expect, it, vi } from 'vitest'

import { getTriggerInputSchemaFields } from './triggerSchemaUtils'

const mockParseTriggerIndex = vi.fn<(nodeId: string) => number | undefined>()

vi.mock('../../../../utils/triggerNodeIds', () => ({
  parseTriggerIndex: (nodeId: string) => mockParseTriggerIndex(nodeId),
}))

describe('getTriggerInputSchemaFields', () => {
  it('exposes the Kafka envelope instead of flattening payload properties into the trigger namespace', () => {
    const fields = getTriggerInputSchemaFields('subscribe', [
      {
        id: 'subscribe',
        type: 'event_subscribe_trigger',
        parameters: { input_schema: { properties: { order_id: { type: 'string' } } } },
      },
    ])
    expect(fields?.map((field) => field.name)).toEqual(['envelope_version', 'payload', 'original', 'metadata'])
  })

  it('returns null when triggersList is undefined', () => {
    expect(getTriggerInputSchemaFields('trigger-1', undefined)).toBeNull()
  })

  it('returns null when trigger not found by ID and index fallback fails', () => {
    mockParseTriggerIndex.mockReturnValue(undefined)

    const triggers = [{ id: 'trigger-other' }]

    expect(getTriggerInputSchemaFields('trigger-1', triggers)).toBeNull()
  })

  it('returns null when trigger found but has no parameters', () => {
    const triggers = [{ id: 'trigger-1' }]

    expect(getTriggerInputSchemaFields('trigger-1', triggers)).toBeNull()
  })

  it('returns null when trigger found but input_schema is missing', () => {
    const triggers = [{ id: 'trigger-1', parameters: { other: 'value' } }]

    expect(getTriggerInputSchemaFields('trigger-1', triggers)).toBeNull()
  })

  it('returns null when input_schema is not an object', () => {
    const triggers = [{ id: 'trigger-1', parameters: { input_schema: 'not-an-object' } }]

    expect(getTriggerInputSchemaFields('trigger-1', triggers)).toBeNull()
  })

  it('returns null when input_schema has no properties', () => {
    const triggers = [{ id: 'trigger-1', parameters: { input_schema: {} } }]

    expect(getTriggerInputSchemaFields('trigger-1', triggers)).toBeNull()
  })

  it('returns null when input_schema.properties is empty', () => {
    const triggers = [
      {
        id: 'trigger-1',
        parameters: {
          input_schema: {
            properties: {},
          },
        },
      },
    ]

    expect(getTriggerInputSchemaFields('trigger-1', triggers)).toBeNull()
  })

  it('returns fields when trigger found by direct ID match', () => {
    const triggers = [
      {
        id: 'trigger-1',
        parameters: {
          input_schema: {
            properties: {
              event_type: { type: 'string', description: 'Event type' },
              payload: { type: 'object', description: 'Event payload' },
            },
          },
        },
      },
    ]

    const result = getTriggerInputSchemaFields('trigger-1', triggers)

    expect(result).toEqual([
      { name: 'event_type', type: 'string', description: 'Event type' },
      { name: 'payload', type: 'object', description: 'Event payload' },
    ])
  })

  it('returns fields when trigger found by index fallback', () => {
    mockParseTriggerIndex.mockReturnValue(0)

    const triggers = [
      {
        id: 'internal-trigger-id',
        parameters: {
          input_schema: {
            properties: {
              timestamp: { type: 'integer', description: 'Event timestamp' },
            },
          },
        },
      },
    ]

    const result = getTriggerInputSchemaFields('trigger_0', triggers)

    expect(result).toEqual([{ name: 'timestamp', type: 'number', description: 'Event timestamp' }])
  })

  it('maps all JSON schema types correctly', () => {
    const triggers = [
      {
        id: 'trigger-1',
        parameters: {
          input_schema: {
            properties: {
              str: { type: 'string' },
              num: { type: 'number' },
              int: { type: 'integer' },
              bool: { type: 'boolean' },
              obj: { type: 'object' },
              arr: { type: 'array' },
            },
          },
        },
      },
    ]

    const result = getTriggerInputSchemaFields('trigger-1', triggers)

    expect(result).toEqual([
      { name: 'str', type: 'string', description: 'Input parameter: str' },
      { name: 'num', type: 'number', description: 'Input parameter: num' },
      { name: 'int', type: 'number', description: 'Input parameter: int' },
      { name: 'bool', type: 'boolean', description: 'Input parameter: bool' },
      { name: 'obj', type: 'object', description: 'Input parameter: obj' },
      { name: 'arr', type: 'array', description: 'Input parameter: arr' },
    ])
  })

  it('maps unknown type to unknown', () => {
    const triggers = [
      {
        id: 'trigger-1',
        parameters: {
          input_schema: {
            properties: {
              unknown_field: { type: 'custom-type' },
            },
          },
        },
      },
    ]

    const result = getTriggerInputSchemaFields('trigger-1', triggers)

    expect(result).toEqual([{ name: 'unknown_field', type: 'unknown', description: 'Input parameter: unknown_field' }])
  })

  it('maps missing type to unknown', () => {
    const triggers = [
      {
        id: 'trigger-1',
        parameters: {
          input_schema: {
            properties: {
              no_type: {},
            },
          },
        },
      },
    ]

    const result = getTriggerInputSchemaFields('trigger-1', triggers)

    expect(result).toEqual([{ name: 'no_type', type: 'unknown', description: 'Input parameter: no_type' }])
  })

  it('uses provided description when available', () => {
    const triggers = [
      {
        id: 'trigger-1',
        parameters: {
          input_schema: {
            properties: {
              field1: { type: 'string', description: 'Custom description' },
              field2: { type: 'number' },
            },
          },
        },
      },
    ]

    const result = getTriggerInputSchemaFields('trigger-1', triggers)

    expect(result).toEqual([
      { name: 'field1', type: 'string', description: 'Custom description' },
      { name: 'field2', type: 'number', description: 'Input parameter: field2' },
    ])
  })

  it('handles index fallback when direct ID match fails', () => {
    mockParseTriggerIndex.mockReturnValue(1)

    const triggers = [
      { id: 'trigger-a' },
      {
        id: 'trigger-b',
        parameters: {
          input_schema: {
            properties: {
              data: { type: 'string', description: 'Data field' },
            },
          },
        },
      },
    ]

    const result = getTriggerInputSchemaFields('trigger_1', triggers)

    expect(result).toEqual([{ name: 'data', type: 'string', description: 'Data field' }])
  })

  it('returns null when index fallback points to undefined trigger', () => {
    mockParseTriggerIndex.mockReturnValue(5)

    const triggers = [{ id: 'trigger-1' }]

    expect(getTriggerInputSchemaFields('trigger_5', triggers)).toBeNull()
  })

  it('returns null when index fallback finds trigger without input_schema', () => {
    mockParseTriggerIndex.mockReturnValue(0)

    const triggers = [{ id: 'trigger-no-schema' }]

    expect(getTriggerInputSchemaFields('trigger_0', triggers)).toBeNull()
  })
})
