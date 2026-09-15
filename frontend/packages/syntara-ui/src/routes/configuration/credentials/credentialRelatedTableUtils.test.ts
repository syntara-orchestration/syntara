import { describe, expect, it } from 'vitest'

import {
  expandableRowIds,
  hasTrimmedDescription,
  RELATED_RESOURCE_DASH,
  relatedResourceRowId,
} from './credentialRelatedTableUtils'

describe('credentialRelatedTableUtils', () => {
  it('treats missing, empty, and whitespace descriptions as absent', () => {
    expect(hasTrimmedDescription(undefined)).toBe(false)
    expect(hasTrimmedDescription(null)).toBe(false)
    expect(hasTrimmedDescription('')).toBe(false)
    expect(hasTrimmedDescription('   \n\t')).toBe(false)
  })

  it('treats non-empty descriptions as present', () => {
    expect(hasTrimmedDescription('Uses GitHub')).toBe(true)
  })

  it('uses the resource id when present', () => {
    expect(relatedResourceRowId('int-1', 'integration', 3)).toBe('int-1')
  })

  it('falls back to a prefixed index when id is missing', () => {
    expect(relatedResourceRowId(undefined, 'integration', 3)).toBe('integration-3')
    expect(relatedResourceRowId(null, 'workflow', 0)).toBe('workflow-0')
  })

  it('returns only ids for rows with a description', () => {
    expect(
      expandableRowIds(
        [
          { id: 'a', description: 'Has description' },
          { id: 'b', description: '' },
          { id: 'c', description: '   ' },
          { description: 'No id' },
        ],
        'row'
      )
    ).toEqual(['a', 'row-3'])
  })

  it('exports an em dash placeholder', () => {
    expect(RELATED_RESOURCE_DASH).toBe('\u2014')
  })
})
