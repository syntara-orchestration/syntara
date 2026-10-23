import { describe, expect, it } from 'vitest'

import {
  formatInputMappingJson,
  getInvocationInputFields,
  parseFreeformInputMapping,
  serializeInvocationInputMapping,
} from './invocationSchemaUtils'

describe('invocationSchemaUtils', () => {
  it('extracts names, types, required fields, descriptions, and defaults from JSON Schema', () => {
    expect(
      getInvocationInputFields({
        type: 'object',
        required: ['host'],
        properties: {
          host: { type: 'string', description: 'Target host' },
          port: { type: 'integer', default: 22 },
        },
      })
    ).toEqual([
      { name: 'host', type: 'string', required: true, description: 'Target host' },
      { name: 'port', type: 'integer', required: false, defaultValue: 22 },
    ])
  })

  it('returns no fields when the child has no declared properties', () => {
    expect(getInvocationInputFields(undefined)).toEqual([])
    expect(getInvocationInputFields({ type: 'object' })).toEqual([])
  })

  it('applies defaults and coerces static values to the child input types', () => {
    const fields = getInvocationInputFields({
      properties: {
        host: { type: 'string' },
        port: { type: 'integer', default: 22 },
        tls: { type: 'boolean' },
        options: { type: 'object' },
        tags: { type: 'array' },
      },
      required: ['host', 'port', 'tls', 'options', 'tags'],
    })

    expect(
      serializeInvocationInputMapping(
        { host: 'server.example', tls: 'false', options: '{"mode":"safe"}', tags: '["ops"]' },
        fields
      )
    ).toEqual({ host: 'server.example', tls: false, options: { mode: 'safe' }, tags: ['ops'] })
  })

  it('preserves template expressions instead of coercing them', () => {
    const fields = getInvocationInputFields({ properties: { port: { type: 'integer' } } })
    expect(serializeInvocationInputMapping({ port: '${steps.lookup.port}' }, fields)).toEqual({
      port: '${steps.lookup.port}',
    })
  })

  it('omits missing required values and rejects values that do not match the declared type', () => {
    const requiredField = getInvocationInputFields({ properties: { host: { type: 'string' } }, required: ['host'] })
    const integerField = getInvocationInputFields({ properties: { port: { type: 'integer' } } })

    expect(serializeInvocationInputMapping({}, requiredField)).toEqual({})
    expect(() => serializeInvocationInputMapping({ port: '2.5' }, integerField)).toThrow('valid integer')
    expect(() =>
      serializeInvocationInputMapping(
        { port: '{bad' },
        getInvocationInputFields({ properties: { port: { type: 'object' } } })
      )
    ).toThrow()
  })

  it('parses the free-form fallback as a JSON object', () => {
    expect(parseFreeformInputMapping('{"region":"east"}')).toEqual({ region: 'east' })
    expect(parseFreeformInputMapping('')).toEqual({})
    expect(() => parseFreeformInputMapping('[]')).toThrow('JSON object')
  })

  it('formats existing mappings as editable JSON', () => {
    expect(formatInputMappingJson({ host: 'server.example' })).toBe(`{
  "host": "server.example"
}`)
  })
})
