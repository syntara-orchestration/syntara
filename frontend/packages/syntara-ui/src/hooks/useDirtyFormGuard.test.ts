import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { DirtyCheckOptions } from '../providers/unsaved-changes/unsavedChangesContext'

import { useDirtyFormGuard } from './useDirtyFormGuard'

const mockUnregister = vi.fn()
const mockRegisterDirtyCheck = vi.fn((() => mockUnregister) as (opts: DirtyCheckOptions) => () => void)

vi.mock('../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({ registerDirtyCheck: mockRegisterDirtyCheck }),
}))

function lastRegistration(): DirtyCheckOptions {
  const calls = mockRegisterDirtyCheck.mock.calls
  return calls[calls.length - 1][0]
}

describe('useDirtyFormGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('registers a dirty check on mount', () => {
    renderHook(() =>
      useDirtyFormGuard({
        isDirty: false,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(1)
    expect(lastRegistration().title).toBe('Save?')
    expect(lastRegistration().body).toBe('Unsaved changes.')
  })

  it('unregisters on unmount', () => {
    const { unmount } = renderHook(() =>
      useDirtyFormGuard({
        isDirty: false,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    unmount()
    expect(mockUnregister).toHaveBeenCalledTimes(1)
  })

  it('check() returns false when isDirty is false', () => {
    renderHook(() =>
      useDirtyFormGuard({
        isDirty: false,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    expect(lastRegistration().check()).toBe(false)
  })

  it('check() returns true when isDirty is true', () => {
    renderHook(() =>
      useDirtyFormGuard({
        isDirty: true,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    expect(lastRegistration().check()).toBe(true)
  })

  it('tracks isDirty changes via ref without re-registering', () => {
    const { rerender } = renderHook(({ isDirty }) => useDirtyFormGuard({ isDirty, title: 'Save?', body: 'Changes.' }), {
      initialProps: { isDirty: false },
    })

    expect(lastRegistration().check()).toBe(false)
    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(1)

    rerender({ isDirty: true })

    expect(lastRegistration().check()).toBe(true)
    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(1)
  })

  it('check() returns false when isActive is false even if isDirty is true', () => {
    renderHook(() =>
      useDirtyFormGuard({
        isDirty: true,
        isActive: false,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    expect(lastRegistration().check()).toBe(false)
  })

  it('calls onSave when saveAndExit is invoked', async () => {
    const onSave = vi.fn().mockResolvedValue(true)

    renderHook(() =>
      useDirtyFormGuard({
        isDirty: true,
        onSave,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    const result = await lastRegistration().saveAndExit!()
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(result).toBe(true)
  })

  it('does not register saveAndExit when onSave is omitted', () => {
    renderHook(() =>
      useDirtyFormGuard({
        isDirty: true,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    expect(lastRegistration().saveAndExit).toBeUndefined()
  })

  it('calls onDiscard and clears isDirty ref when exitWithoutSaving is invoked', () => {
    const onDiscard = vi.fn()

    renderHook(() =>
      useDirtyFormGuard({
        isDirty: true,
        onDiscard,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    expect(lastRegistration().check()).toBe(true)

    act(() => {
      lastRegistration().exitWithoutSaving!()
    })

    expect(onDiscard).toHaveBeenCalledTimes(1)
    expect(lastRegistration().check()).toBe(false)
  })

  it('registers exitWithoutSaving even when onDiscard is omitted', () => {
    renderHook(() =>
      useDirtyFormGuard({
        isDirty: true,
        title: 'Save?',
        body: 'Unsaved changes.',
      })
    )

    expect(lastRegistration().exitWithoutSaving).toBeDefined()
    lastRegistration().exitWithoutSaving!()
    expect(lastRegistration().check()).toBe(false)
  })

  it('passes saveLabel through to registerDirtyCheck', () => {
    renderHook(() =>
      useDirtyFormGuard({
        isDirty: false,
        title: 'Save settings?',
        body: 'Unsaved settings.',
        saveLabel: 'Save settings',
      })
    )

    expect(lastRegistration().saveLabel).toBe('Save settings')
  })

  it('re-registers when title changes', () => {
    const { rerender } = renderHook(({ title }) => useDirtyFormGuard({ isDirty: false, title, body: 'Changes.' }), {
      initialProps: { title: 'Save?' },
    })

    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(1)

    rerender({ title: 'Save settings?' })

    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(2)
    expect(mockUnregister).toHaveBeenCalledTimes(1)
  })

  it('re-registers when isActive changes', () => {
    const { rerender } = renderHook(
      ({ isActive }) => useDirtyFormGuard({ isDirty: true, isActive, title: 'Save?', body: 'Changes.' }),
      { initialProps: { isActive: true } }
    )

    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(1)

    rerender({ isActive: false })

    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(2)
  })

  it('uses latest onSave without re-registering', async () => {
    const onSave1 = vi.fn().mockResolvedValue(true)
    const onSave2 = vi.fn().mockResolvedValue(true)

    const { rerender } = renderHook(
      ({ onSave }) => useDirtyFormGuard({ isDirty: true, onSave, title: 'Save?', body: 'Changes.' }),
      { initialProps: { onSave: onSave1 } }
    )

    rerender({ onSave: onSave2 })

    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(1)

    await lastRegistration().saveAndExit!()
    expect(onSave1).not.toHaveBeenCalled()
    expect(onSave2).toHaveBeenCalledTimes(1)
  })

  it('uses latest onDiscard without re-registering', () => {
    const onDiscard1 = vi.fn()
    const onDiscard2 = vi.fn()

    const { rerender } = renderHook(
      ({ onDiscard }) => useDirtyFormGuard({ isDirty: true, onDiscard, title: 'Save?', body: 'Changes.' }),
      { initialProps: { onDiscard: onDiscard1 } }
    )

    rerender({ onDiscard: onDiscard2 })

    expect(mockRegisterDirtyCheck).toHaveBeenCalledTimes(1)

    act(() => {
      lastRegistration().exitWithoutSaving!()
    })

    expect(onDiscard1).not.toHaveBeenCalled()
    expect(onDiscard2).toHaveBeenCalledTimes(1)
  })
})
