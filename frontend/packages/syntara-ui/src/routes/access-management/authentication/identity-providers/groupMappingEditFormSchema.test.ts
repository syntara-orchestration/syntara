import { describe, expect, it } from 'vitest'

import {
  GROUP_MAPPING_IDP_GROUP_VALUE_MAX_LENGTH,
  GROUP_MAPPING_JMESPATH_EXPRESSION_MAX_LENGTH,
  groupMappingEditFormSchema,
} from './groupMappingEditFormSchema'

const VALID_GROUP_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

describe('groupMappingEditFormSchema', () => {
  it('accepts a complete mapping row and valid JMESPath expression', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'groups[*]',
      entries: [{ idpGroupValue: 'admin', mappedGroupId: VALID_GROUP_ID }],
    })

    expect(result.success).toBe(true)
  })

  it('accepts empty entries when clearing all mappings', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'groups[*]',
      entries: [],
    })

    expect(result.success).toBe(true)
  })

  it('accepts blank rows that are filtered out on save', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'groups[*]',
      entries: [{ idpGroupValue: '', mappedGroupId: '' }],
    })

    expect(result.success).toBe(true)
  })

  it('rejects IdP group values over the max length', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'groups[*]',
      entries: [{ idpGroupValue: 'a'.repeat(GROUP_MAPPING_IDP_GROUP_VALUE_MAX_LENGTH + 1), mappedGroupId: '' }],
    })

    expect(result.success).toBe(false)
  })

  it('rejects invalid Syntara group IDs', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'groups[*]',
      entries: [{ idpGroupValue: 'admin', mappedGroupId: 'not-a-uuid' }],
    })

    expect(result.success).toBe(false)
  })

  it('rejects JMESPath expressions over the max length', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'a'.repeat(GROUP_MAPPING_JMESPATH_EXPRESSION_MAX_LENGTH + 1),
      entries: [],
    })

    expect(result.success).toBe(false)
  })

  it('rejects invalid JMESPath syntax', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'groups[[[*]',
      entries: [],
    })

    expect(result.success).toBe(false)
  })

  it('rejects partial rows missing a Syntara group', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'groups[*]',
      entries: [{ idpGroupValue: 'admin', mappedGroupId: '' }],
    })

    expect(result.success).toBe(false)
  })

  it('rejects partial rows missing an IdP group value', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: 'groups[*]',
      entries: [{ idpGroupValue: '', mappedGroupId: VALID_GROUP_ID }],
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((issue) => issue.message === 'Enter an IdP group value')).toBe(true)
    }
  })

  it('rejects empty JMESPath expression', () => {
    const result = groupMappingEditFormSchema.safeParse({
      expression: '',
      entries: [],
    })

    expect(result.success).toBe(false)
  })
})
