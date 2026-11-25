import { act, renderHook } from '@testing-library/react'
import { type Dispatch, useRef } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { BuilderAction } from '../builderReducer'

import { useGuardedSaveWorkflow } from './useGuardedSaveWorkflow'

type AutoSubmitFn = () => Promise<boolean>

function renderGuard(
  overrides: {
    isStepEditorOpen?: boolean
    stepEditorMode?: 'add' | 'edit' | null
    autoSubmitFn?: AutoSubmitFn | null
    handleSaveWorkflow?: (options?: { expectedVersionOverride?: number }) => Promise<boolean>
  } = {}
) {
  const dispatch: Dispatch<BuilderAction> = vi.fn()
  const handleSaveWorkflow = overrides.handleSaveWorkflow ?? vi.fn().mockResolvedValue(true)

  const utils = renderHook(() => {
    const autoSubmitRef = useRef<AutoSubmitFn | null>(overrides.autoSubmitFn ?? null)
    return useGuardedSaveWorkflow({
      handleSaveWorkflow,
      isStepEditorOpen: overrides.isStepEditorOpen ?? false,
      stepEditorMode: overrides.stepEditorMode ?? null,
      autoSubmitRef,
      dispatch,
    })
  })

  return { ...utils, dispatch, handleSaveWorkflow }
}

describe('useGuardedSaveWorkflow', () => {
  it('calls handleSaveWorkflow directly when step editor is closed', async () => {
    const { result, handleSaveWorkflow } = renderGuard({ isStepEditorOpen: false })

    await act(async () => {
      await result.current()
    })

    expect(handleSaveWorkflow).toHaveBeenCalledOnce()
  })

  it('shows dialog and blocks save in add mode', async () => {
    const { result, dispatch, handleSaveWorkflow } = renderGuard({
      isStepEditorOpen: true,
      stepEditorMode: 'add',
    })

    let returned: boolean | undefined
    await act(async () => {
      returned = await result.current()
    })

    expect(returned).toBe(false)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_UNSAVED_STEP_EDITOR_DIALOG', payload: true })
    expect(handleSaveWorkflow).not.toHaveBeenCalled()
  })

  it('shows dialog when edit mode has no auto-submit registered', async () => {
    const { result, dispatch, handleSaveWorkflow } = renderGuard({
      isStepEditorOpen: true,
      stepEditorMode: 'edit',
      autoSubmitFn: null,
    })

    let returned: boolean | undefined
    await act(async () => {
      returned = await result.current()
    })

    expect(returned).toBe(false)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_UNSAVED_STEP_EDITOR_DIALOG', payload: true })
    expect(handleSaveWorkflow).not.toHaveBeenCalled()
  })

  it('auto-submits and saves when auto-submit succeeds in edit mode', async () => {
    const autoSubmitFn = vi.fn().mockResolvedValue(true)
    const { result, dispatch, handleSaveWorkflow } = renderGuard({
      isStepEditorOpen: true,
      stepEditorMode: 'edit',
      autoSubmitFn,
    })

    await act(async () => {
      await result.current()
    })

    expect(autoSubmitFn).toHaveBeenCalledOnce()
    expect(handleSaveWorkflow).toHaveBeenCalledOnce()
    expect(dispatch).not.toHaveBeenCalled()
  })

  it('returns false without dialog when auto-submit validation fails in edit mode', async () => {
    const autoSubmitFn = vi.fn().mockResolvedValue(false)
    const { result, dispatch, handleSaveWorkflow } = renderGuard({
      isStepEditorOpen: true,
      stepEditorMode: 'edit',
      autoSubmitFn,
    })

    let returned: boolean | undefined
    await act(async () => {
      returned = await result.current()
    })

    expect(returned).toBe(false)
    expect(autoSubmitFn).toHaveBeenCalledOnce()
    expect(handleSaveWorkflow).not.toHaveBeenCalled()
    expect(dispatch).not.toHaveBeenCalled()
  })
})
