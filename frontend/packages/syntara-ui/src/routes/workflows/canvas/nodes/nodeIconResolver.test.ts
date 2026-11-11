import { describe, expect, it } from 'vitest'

import { getCanvasNodeIconDescriptor, getTaskIconDescriptor } from './nodeIconResolver'
import { getCanvasStepIconDescriptor, getTaskIconDescriptor as getStepTaskIconDescriptor } from './stepIconResolver'

describe('legacy node icon resolver exports', () => {
  it('delegates canvas descriptors to the step implementation used by builder callers', () => {
    expect(getCanvasNodeIconDescriptor).toBe(getCanvasStepIconDescriptor)
  })

  it('re-exports the shared task icon resolver', () => {
    expect(getTaskIconDescriptor).toBe(getStepTaskIconDescriptor)
  })
})
