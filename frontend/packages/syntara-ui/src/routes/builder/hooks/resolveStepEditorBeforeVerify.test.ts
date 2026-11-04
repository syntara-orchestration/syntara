import { describe, expect, it, vi } from 'vitest'

import type { BuilderAction } from '../builderReducer'

import { resolveStepEditorBeforeVerify } from './resolveStepEditorBeforeVerify'

describe('resolveStepEditorBeforeVerify', () => {
  const dispatch = vi.fn<(action: BuilderAction) => void>()

  it('returns true when the node editor is closed', async () => {
    const ready = await resolveStepEditorBeforeVerify({
      isNodeEditorOpen: false,
      nodeEditorMode: null,
      autoSubmitRef: { current: null },
      dispatch,
    })
    expect(ready).toBe(true)
    expect(dispatch).not.toHaveBeenCalled()
  })

  it('auto-submits in edit mode when a handler is registered', async () => {
    const autoSubmit = vi.fn().mockResolvedValue(true)
    const ready = await resolveStepEditorBeforeVerify({
      isNodeEditorOpen: true,
      nodeEditorMode: 'edit',
      autoSubmitRef: { current: autoSubmit },
      dispatch,
    })
    expect(ready).toBe(true)
    expect(autoSubmit).toHaveBeenCalledOnce()
  })

  it('blocks verify in add mode and opens the unsaved dialog', async () => {
    const ready = await resolveStepEditorBeforeVerify({
      isNodeEditorOpen: true,
      nodeEditorMode: 'add',
      autoSubmitRef: { current: null },
      dispatch,
    })
    expect(ready).toBe(false)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_UNSAVED_STEP_EDITOR_DIALOG', payload: true })
  })

  it('blocks verify in edit mode when auto-submit is not registered', async () => {
    const ready = await resolveStepEditorBeforeVerify({
      isNodeEditorOpen: true,
      nodeEditorMode: 'edit',
      autoSubmitRef: { current: null },
      dispatch,
    })
    expect(ready).toBe(false)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_UNSAVED_STEP_EDITOR_DIALOG', payload: true })
  })
})
