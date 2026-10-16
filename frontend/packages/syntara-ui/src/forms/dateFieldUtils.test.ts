import { describe, expect, it } from 'vitest'

import {
  isSoleIncludedDateComponent,
  normalizeDateDefaultForIncludes,
  nextDateIncludes,
  prepareFormDefinitionForCommit,
} from './dateFieldUtils'
import { safeParseFormDefinition } from './formDefinitionSchema'
import { FormFieldTypeEnum } from './formFieldTypeEnum'

describe('dateFieldUtils', () => {
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

  it('prepareFormDefinitionForCommit repairs time without timezone for API validation', () => {
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
    const parsed = safeParseFormDefinition(prepared)
    expect(parsed.success).toBe(true)
    if (parsed.success) {
      const field = parsed.data.fields[0]
      expect(field.type).toBe('date')
      if (field.type === 'date') {
        expect(field.include_timezone).toBe(true)
      }
    }
  })
})
