import { describe, expect, it } from 'vitest'

import { buildTFEParameters, resourceAddressesToCsv } from './tfeHelpers'

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
