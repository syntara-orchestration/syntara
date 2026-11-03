import { describe, expect, it, vi } from 'vitest'

import { getStepDisplayName, getStepDisplayNameForEdit } from './stepNaming'

const mockWorkflowState = vi.hoisted(() => ({
  currentWorkflow: {
    triggers: [{ name: 'Trigger' }],
    workflow: {
      activities: [{ name: 'Script' }, { name: 'Script2' }],
    },
  },
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => mockWorkflowState),
  },
}))

vi.mock('../../../utils/generateUUID', () => ({
  generateUUID: vi.fn(() => '00000000-0000-0000-0000-000000000000'),
}))

describe('stepNaming', () => {
  it('generates unique names when requested name collides', () => {
    expect(getStepDisplayName('Script', 'Script')).toBe('Script3')
  })

  it('generates unique names when base name collides', () => {
    expect(getStepDisplayName('Script')).toBe('Script3')
  })

  it('uses random fallback when base name is blank', () => {
    expect(getStepDisplayName('')).toBe('Step-00000000')
  })

  it('keeps current name on edit when unchanged', () => {
    expect(getStepDisplayNameForEdit('Trigger', 'Trigger', 'Trigger')).toBe('Trigger')
  })

  it('avoids conflicts when editing to a new name', () => {
    expect(getStepDisplayNameForEdit('Trigger', 'Script', 'Trigger')).toBe('Script3')
  })
})
