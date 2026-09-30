import { describe, expect, it } from 'vitest'

import { buildTFEParameters, resourceAddressesToCsv } from './tfeHelpers'

describe('buildTFEParameters sensitive variables', () => {
  it('omits plaintext value when sensitive and keeps value_credential_id', () => {
    const params = buildTFEParameters({
      name: 'Add var',
      workspace_id: 'ws-1',
      key: 'DB_PASSWORD',
      value: 'should-not-persist',
      sensitive: true,
      value_credential_id: '33333333-3333-3333-3333-333333333333',
    })
    expect(params.value).toBeUndefined()
    expect(params.value_credential_id).toBe('33333333-3333-3333-3333-333333333333')
    expect(params.sensitive).toBe(true)
  })

  it('keeps plaintext value when not sensitive', () => {
    const params = buildTFEParameters({
      name: 'Add var',
      workspace_id: 'ws-1',
      key: 'REGION',
      value: 'us-east-1',
      sensitive: false,
    })
    expect(params.value).toBe('us-east-1')
    expect(params.value_credential_id).toBeUndefined()
  })
})

describe('Terraform resource address editing', () => {
  it.each(['target_resources', 'replace_resources'] as const)('round-trips saved %s', (field) => {
    const saved = buildTFEParameters({ name: 'Run', [field]: 'aws_instance.web, aws_instance.worker' })
    const reopened = { name: 'Renamed run', [field]: resourceAddressesToCsv(saved[field]) }
    expect(buildTFEParameters(reopened)[field]).toEqual(['aws_instance.web', 'aws_instance.worker'])
  })

  it('preserves template strings', () => {
    expect(resourceAddressesToCsv('${trigger.resources}')).toBe('${trigger.resources}')
  })

  it('handles missing and invalid values', () => {
    expect(resourceAddressesToCsv(undefined)).toBeUndefined()
    expect(resourceAddressesToCsv([42])).toBeUndefined()
    expect(resourceAddressesToCsv([])).toBe('')
  })
})
