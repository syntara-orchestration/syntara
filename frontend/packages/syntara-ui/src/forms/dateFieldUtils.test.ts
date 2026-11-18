import { describe, expect, it } from 'vitest'

import {
  isDateFieldDateAndTimezoneWithoutTime,
  isSoleIncludedDateComponent,
  isSupportedRfc3339DateFieldCombination,
  isUnsupportedRfc3339DateFieldCombination,
  normalizeDateDefaultForIncludes,
  nextDateIncludes,
  prepareFormDefinitionForCommit,
} from './dateFieldUtils'
import { safeParseFormDefinition } from './formDefinitionSchema'
import { FormFieldTypeEnum } from './formFieldTypeEnum'

describe('dateFieldUtils', () => {
  it('recognizes RFC 3339 include combinations', () => {
    expect(isSupportedRfc3339DateFieldCombination({ date: true, time: false, timezone: false })).toBe(true)
    expect(isSupportedRfc3339DateFieldCombination({ date: false, time: true, timezone: true })).toBe(true)
    expect(isSupportedRfc3339DateFieldCombination({ date: true, time: true, timezone: false })).toBe(false)
    expect(
      isUnsupportedRfc3339DateFieldCombination({
        type: FormFieldTypeEnum.DATE,
        value_name: 'due',
        label: 'Due',
        include_date: true,
        include_time: true,
        include_timezone: false,
      })
    ).toBe(true)
  })

  it('detects date and timezone without time', () => {
    expect(
      isDateFieldDateAndTimezoneWithoutTime({
        type: FormFieldTypeEnum.DATE,
        value_name: 'due',
        label: 'Due',
        include_date: true,
        include_timezone: true,
        include_time: false,
      })
    ).toBe(true)
    expect(
      isDateFieldDateAndTimezoneWithoutTime({
        type: FormFieldTypeEnum.DATE,
        value_name: 'due',
        label: 'Due',
        include_date: true,
        include_timezone: true,
        include_time: true,
      })
    ).toBe(false)
  })

  it('marks the sole included component as locked', () => {
    const onlyDate = { date: true, time: false, timezone: false }
    expect(isSoleIncludedDateComponent(onlyDate, 'date')).toBe(true)
    expect(isSoleIncludedDateComponent(onlyDate, 'time')).toBe(false)
    expect(isSoleIncludedDateComponent({ date: true, time: false, timezone: true }, 'date')).toBe(false)
  })

  it('clears incomplete defaults when new components are included', () => {
    expect(
      normalizeDateDefaultForIncludes({ date: '2026-01-02' }, { date: true, time: true, timezone: true })
    ).toBeNull()
  })

  it('toggles time without changing timezone', () => {
    expect(nextDateIncludes({ date: true, time: false, timezone: false }, 'time', true)).toEqual({
      date: true,
      time: true,
      timezone: false,
    })
  })

  it('toggles timezone without changing time', () => {
    expect(nextDateIncludes({ date: true, time: true, timezone: false }, 'timezone', true)).toEqual({
      date: true,
      time: true,
      timezone: true,
    })
    expect(nextDateIncludes({ date: true, time: true, timezone: true }, 'timezone', false)).toEqual({
      date: true,
      time: true,
      timezone: false,
    })
  })

  it('prepareFormDefinitionForCommit preserves include flags without coercing unsupported combinations', () => {
    const prepared = prepareFormDefinitionForCommit({
      fields: [
        {
          type: FormFieldTypeEnum.DATE,
          value_name: 'due',
          label: 'Due',
          include_date: true,
          include_time: true,
          include_timezone: false,
        },
      ],
    })
    expect(safeParseFormDefinition(prepared).success).toBe(false)
    const field = prepared.fields[0]
    expect(field.type).toBe('date')
    if (field.type === 'date') {
      expect(field.include_timezone).toBe(false)
    }
  })
})
