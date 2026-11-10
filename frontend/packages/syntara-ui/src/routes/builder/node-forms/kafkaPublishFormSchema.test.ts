import type { WorkflowAPI } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import {
  buildKafkaPublishParameters,
  kafkaPublishFormSchema,
  kafkaPublishInitialFields,
  kafkaPublishParametersSchema,
} from './kafkaPublishFormSchema'

const valid = {
  name: 'Publish result',
  integration_id: '11111111-1111-4111-8111-111111111111',
  credential_id: '22222222-2222-4222-8222-222222222222',
  connection_ready: true,
  topic: 'automation.outcomes',
  payload: 'null',
  key: { encoding: 'null', value: '' },
  headers_mode: 'entries',
  headers: [],
  headers_template: '',
  settings: {},
}

describe('Kafka Publish form contract', () => {
  it.each([
    'null',
    'false',
    'true',
    '0',
    '42',
    '-1.5',
    '""',
    '"hello"',
    '"{\\"ok\\":true}"',
    '[]',
    '[1,2]',
    '{"ok":true}',
    '${trigger.payload}',
    '"${trigger.payload}"',
  ])('accepts JSON or a full template: %s', (payload) => {
    const data = kafkaPublishFormSchema.parse({ ...valid, payload })
    const parameters = buildKafkaPublishParameters(data)
    expect(parameters.payload).toEqual(payload.startsWith('${') ? payload : JSON.parse(payload))
    const reopened = kafkaPublishFormSchema.parse({ ...valid, ...kafkaPublishInitialFields(parameters) })
    expect(buildKafkaPublishParameters(reopened)).toEqual(parameters)
  })

  it.each(['', 'not json', '1e400', '{"nested":1e400}'])('rejects invalid or non-finite JSON: %s', (payload) => {
    expect(kafkaPublishFormSchema.safeParse({ ...valid, payload }).success).toBe(false)
  })

  it.each(['${trigger.topic}', '..', 'topic with spaces'])('rejects dynamic or invalid destinations: %s', (topic) => {
    expect(kafkaPublishFormSchema.safeParse({ ...valid, topic }).success).toBe(false)
  })

  it('preserves binary keys, header order, duplicate names and null/empty values', () => {
    const key = { encoding: 'base64', value: 'AAEC' }
    const headers: WorkflowAPI.components['schemas']['KafkaPublishHeader'][] = [
      { name: 'x', value: null },
      { name: 'x', value: { encoding: 'utf-8', value: '' } },
    ]
    const data = kafkaPublishFormSchema.parse({
      ...valid,
      ...kafkaPublishInitialFields({
        integration_id: valid.integration_id,
        credential_id: valid.credential_id,
        topic: valid.topic,
        payload: null,
        key: { encoding: 'base64', value: 'AAEC' },
        headers: [...headers, { name: 'binary', value: { encoding: 'base64', value: '' } }],
      }),
    })
    expect(buildKafkaPublishParameters(data)).toMatchObject({
      payload: null,
      key,
      headers: [...headers, { name: 'binary', value: { encoding: 'base64', value: '' } }],
      credential_id: valid.credential_id,
    })
  })

  it('preserves a whole-list header template', () => {
    const data = kafkaPublishFormSchema.parse({
      ...valid,
      headers_mode: 'template',
      headers_template: '${trigger.payload.headers}',
    })
    expect(buildKafkaPublishParameters(data).headers).toBe('${trigger.payload.headers}')
  })

  it('rejects a header dictionary and numeric encoded values', () => {
    expect(kafkaPublishFormSchema.safeParse({ ...valid, headers: { x: 'value' } }).success).toBe(false)
    expect(kafkaPublishFormSchema.safeParse({ ...valid, key: { encoding: 'utf-8', value: 42 } }).success).toBe(false)
  })

  it.each(['bad base64', 'AAE', 'AA_E', 'AAEC\n', '='])(
    'rejects invalid Base64 in keys and header values: %s',
    (value) => {
      expect(kafkaPublishFormSchema.safeParse({ ...valid, key: { encoding: 'base64', value } }).success).toBe(false)
      expect(
        kafkaPublishFormSchema.safeParse({ ...valid, headers: [{ name: 'x', encoding: 'base64', value }] }).success
      ).toBe(false)
    }
  )

  it.each(['', 'AAEC', 'AA==', '${trigger.payload.bytes}'])(
    'accepts explicit Base64 or templated bytes: %s',
    (value) => {
      const data = kafkaPublishFormSchema.parse({ ...valid, key: { encoding: 'base64', value } })
      expect(buildKafkaPublishParameters(data).key).toEqual({ encoding: 'base64', value })
    }
  )

  it('counts repeated and null headers toward the limit', () => {
    const entry = { name: 'x', encoding: 'null', value: '' }
    expect(
      kafkaPublishFormSchema.safeParse({ ...valid, headers: Array.from({ length: 128 }, () => entry) }).success
    ).toBe(true)
    const result = kafkaPublishFormSchema.safeParse({ ...valid, headers: Array.from({ length: 129 }, () => entry) })
    expect(result.success).toBe(false)
    if (!result.success) expect(result.error.issues).toContainEqual(expect.objectContaining({ path: ['headers'] }))
  })

  it.each(['', null, undefined])('requires a runtime credential: %s', (credential_id) => {
    const result = kafkaPublishFormSchema.safeParse({ ...valid, credential_id })
    expect(result.success).toBe(false)
    if (!result.success)
      expect(result.error.issues).toContainEqual(
        expect.objectContaining({ path: ['credential_id'], message: 'Select a runtime Kafka credential' })
      )
  })

  it.each([null, undefined])('opens incomplete saved drafts for credential correction: %s', (credential_id) => {
    const saved = kafkaPublishParametersSchema.parse({
      integration_id: valid.integration_id,
      credential_id,
      topic: valid.topic,
      payload: null,
    })
    const fields = kafkaPublishInitialFields(saved)
    expect(fields.credential_id).toBe('')
    expect(kafkaPublishFormSchema.safeParse({ ...valid, ...fields }).success).toBe(false)
  })

  it('blocks an unloaded connection without marking the selected integration as invalid', () => {
    const result = kafkaPublishFormSchema.safeParse({ ...valid, connection_ready: false })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues).toContainEqual(expect.objectContaining({ path: ['connection_ready'] }))
      expect(result.error.issues).not.toContainEqual(expect.objectContaining({ path: ['integration_id'] }))
    }
  })

  it.each(['integration_id', 'credential_id'])('rejects a templated %s', (name) => {
    expect(kafkaPublishFormSchema.safeParse({ ...valid, [name]: '${trigger.id}' }).success).toBe(false)
  })

  it('validates only the active header source and preserves zero additional retries', () => {
    const data = kafkaPublishFormSchema.parse({
      ...valid,
      headers_mode: 'template',
      headers_template: '${trigger.headers}',
      headers: [{ name: 'draft', encoding: 'base64', value: 'invalid' }],
      settings: { timeout: 30, retry_policy: { max_retries: 0 } },
    })
    expect(buildKafkaPublishParameters(data).headers).toBe('${trigger.headers}')
    expect(data.settings).toEqual({ timeout: 30, retry_policy: { max_retries: 0 } })
    expect(
      kafkaPublishFormSchema.safeParse({ ...valid, headers_mode: 'template', headers_template: 'plain text' }).success
    ).toBe(false)
  })

  it('rejects malformed saved wire structures without coercing their values', () => {
    const parameters = { integration_id: valid.integration_id, topic: valid.topic, payload: null }
    expect(
      kafkaPublishParametersSchema.safeParse({ ...parameters, key: { encoding: 'utf-8', value: 42 } }).success
    ).toBe(false)
    expect(kafkaPublishParametersSchema.safeParse({ ...parameters, headers: { x: 'value' } }).success).toBe(false)
    expect(kafkaPublishParametersSchema.safeParse({ ...parameters, headers: [{ name: 'x' }] }).success).toBe(false)
  })
})
