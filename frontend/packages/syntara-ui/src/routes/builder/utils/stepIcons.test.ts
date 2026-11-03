import type { ComponentType } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { getCanvasStepIconDescriptor } from '../../workflows/canvas/nodes/stepIconResolver'

import { resolveIconForStep, resolveIconForType } from './stepIcons'

const mockStepRegistryGetAll = vi.hoisted(() => vi.fn())

vi.mock('../registry/StepRegistry', () => ({
  StepRegistry: {
    getAll: mockStepRegistryGetAll,
  },
}))

vi.mock('../../workflows/canvas/nodes/stepIconResolver', () => ({
  getCanvasStepIconDescriptor: vi.fn(),
}))

describe('stepIcons', () => {
  const IconA: ComponentType = () => null
  const IconB: ComponentType = () => null

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('resolves icons for registry node types and subtypes', () => {
    mockStepRegistryGetAll.mockReturnValue([
      {
        id: 'action',
        icon: IconA,
        subtypes: [{ id: 'action-script', icon: IconB }],
      },
    ] as never[])

    expect(resolveIconForType({ stepTypeId: 'action' })).toEqual({ icon: IconA, id: 'action' })
    expect(resolveIconForType({ stepTypeId: 'action', stepSubtypeId: 'action-script' })).toEqual({
      icon: IconB,
      id: 'action-script',
    })
  })

  it('returns undefined icon when no registry match is found', () => {
    mockStepRegistryGetAll.mockReturnValue([] as never[])

    expect(resolveIconForType({ stepTypeId: 'missing' })).toEqual({ icon: undefined, id: 'missing' })
    expect(resolveIconForType({ stepTypeId: null, stepSubtypeId: null })).toEqual({ icon: undefined, id: undefined })
  })

  it('delegates node icon resolution to the canvas resolver', () => {
    vi.mocked(getCanvasStepIconDescriptor).mockReturnValue({ icon: IconA, id: 'logic-condition' })

    const result = resolveIconForStep(
      {
        id: 'condition-1',
        type: 'condition',
        data: { id: 'condition-1', type: 'condition' },
      } as never,
      { triggers: [] }
    )

    expect(getCanvasStepIconDescriptor).toHaveBeenCalled()
    expect(result).toEqual({ icon: IconA, id: 'logic-condition' })
  })
})
