import { describe, expect, it } from 'vitest'

import {
  dateDefaultCoversAllIncludedComponents,
  isSoleIncludedDateComponent,
  getDateDefaultCompletenessError,
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

  it('preserves partial defaults when new components are included', () => {
    // Partial defaults are allowed — only extra (uncollected) components are pruned.
    expect(normalizeDateDefaultForIncludes({ date: '2026-01-02' }, { date: true, time: true, timezone: true })).toEqual(
      { date: '2026-01-02' }
    )
    // Clears when ALL included parts are empty.
    expect(normalizeDateDefaultForIncludes({}, { date: true, time: true, timezone: false })).toBeNull()
  })

  it('prunes extra default components that the field does not collect', () => {
    // date-only field: time/timezone in the default are extra → pruned out.
    expect(
      normalizeDateDefaultForIncludes(
        { date: '2026-01-02', time: '10:00', timezone: 'UTC' },
        { date: true, time: false, timezone: false }
      )
    ).toEqual({ date: '2026-01-02' })
  })

  it('reports extra default components but not missing ones', () => {
    // Partial (only date, field collects date+time) → no error.
    expect(getDateDefaultCompletenessError({ date: '2026-03-15' }, ['date', 'time'])).toBeUndefined()
    // Extra component → error.
    expect(getDateDefaultCompletenessError({ date: '2026-03-15', time: '10:00' }, ['date'])).toBe(
      'Default supplies time, which this field does not collect'
    )
    expect(getDateDefaultCompletenessError(null, ['date', 'time'])).toBeUndefined()
  })

  it('detects when a default covers all included date components', () => {
    const partial = {
      type: 'date' as const,
      value_name: 'd',
      label: 'D',
      include_date: true,
      include_time: true,
      include_timezone: true,
      default: { date: '2026-01-15' },
    }
    expect(dateDefaultCoversAllIncludedComponents(partial)).toBe(false)

    const complete = {
      ...partial,
      default: { date: '2026-01-15', time: '10:00', timezone: 'UTC' },
    }
    expect(dateDefaultCoversAllIncludedComponents(complete)).toBe(true)
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

  it('prepareFormDefinitionForCommit preserves date and time without timezone', () => {
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
        expect(field.include_timezone).toBe(false)
      }
    }
  })
})
