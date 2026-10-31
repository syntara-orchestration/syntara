import { describe, expect, it } from 'vitest'

import { buildKafkaPublishParameters, kafkaPublishFormSchema } from './kafkaPublishFormSchema'

const valid = {
  name: 'Publish result',
  integration_id: '11111111-1111-4111-8111-111111111111',
  credential_id: '',
  topic: 'automation.outcomes',
  payload: 'null',
  key: '',
  headers: '[]',
  settings: {},
}

describe('Kafka Publish form contract', () => {
  it.each(['null', 'false', '42', '"hello"', '[1,2]', '{"ok":true}', '${trigger.payload}'])(
    'accepts JSON or a full template: %s',
    (payload) => {
      const data = kafkaPublishFormSchema.parse({ ...valid, payload })
      const parameters = buildKafkaPublishParameters(data)
      expect(parameters.payload).toEqual(payload.startsWith('${') ? payload : JSON.parse(payload))
    }
  )

  it.each(['', 'not json', '1e400', '{"nested":1e400}'])('rejects invalid or non-finite JSON: %s', (payload) => {
    expect(kafkaPublishFormSchema.safeParse({ ...valid, payload }).success).toBe(false)
  })

  it.each(['${trigger.topic}', '..', 'topic with spaces'])('rejects dynamic or invalid destinations: %s', (topic) => {
    expect(kafkaPublishFormSchema.safeParse({ ...valid, topic }).success).toBe(false)
  })

  it('preserves binary keys, header order, duplicate names and null/empty values', () => {
    const key = { encoding: 'base64', value: 'AAEC' }
    const headers = [
      { name: 'x', value: null },
      { name: 'x', value: { encoding: 'utf-8', value: '' } },
    ]
    const data = kafkaPublishFormSchema.parse({ ...valid, key: JSON.stringify(key), headers: JSON.stringify(headers) })
    expect(buildKafkaPublishParameters(data)).toMatchObject({ payload: null, key, headers, credential_id: null })
  })

  it('preserves a whole-list header template', () => {
    const data = kafkaPublishFormSchema.parse({ ...valid, headers: '${trigger.payload.headers}' })
    expect(buildKafkaPublishParameters(data).headers).toBe('${trigger.payload.headers}')
  })

  it('rejects a header dictionary and numeric encoded values', () => {
    expect(kafkaPublishFormSchema.safeParse({ ...valid, headers: '{"x":"value"}' }).success).toBe(false)
    expect(kafkaPublishFormSchema.safeParse({ ...valid, key: '{"encoding":"utf-8","value":42}' }).success).toBe(false)
  })
})
