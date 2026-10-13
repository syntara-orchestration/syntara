import { describe, expect, it } from 'vitest'

import { getCategoryMetadata, NODE_CATEGORY_DISPLAY_ORDER } from './categories'

describe('registry categories', () => {
  it('lists human_tasks before integration in the add-step panel order', () => {
    expect(NODE_CATEGORY_DISPLAY_ORDER.indexOf('human_tasks')).toBeLessThan(
      NODE_CATEGORY_DISPLAY_ORDER.indexOf('integration')
    )
  })

  it('exposes human_tasks category metadata', () => {
    const metadata = getCategoryMetadata('human_tasks')
    expect(metadata?.id).toBe('human_tasks')
    expect(metadata?.label).toBe('Human tasks')
    expect(metadata?.order).toBe(45)
  })

  it('returns undefined when category metadata is not defined', () => {
    expect(getCategoryMetadata(undefined)).toBeUndefined()
    expect(getCategoryMetadata('trigger')).toBeUndefined()
  })
})
