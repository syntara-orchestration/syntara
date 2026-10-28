import { describe, expect, it } from 'vitest'

import { parseFormDefinition } from '../../../forms'

import { buildDefaultValues } from './buildDefaultValues'

describe('buildDefaultValues', () => {
  it('prefills a partial date initial answer for editing in the run form', () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: 'date',
          value_name: 'start',
          label: 'Start',
          required: false,
          include_date: true,
          include_time: true,
          include_timezone: true,
          default: { date: '2026-03-01' },
        },
      ],
    })

    expect(buildDefaultValues(definition)).toEqual({ start: { date: '2026-03-01' } })
  })

  it('prefills a complete date initial answer', () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: 'date',
          value_name: 'start',
          label: 'Start',
          include_date: true,
          include_time: true,
          include_timezone: true,
          default: { date: '2026-03-01', time: '08:00', timezone: 'UTC' },
        },
      ],
    })

    expect(buildDefaultValues(definition)).toEqual({
      start: { date: '2026-03-01', time: '08:00', timezone: 'UTC' },
    })
  })
})
