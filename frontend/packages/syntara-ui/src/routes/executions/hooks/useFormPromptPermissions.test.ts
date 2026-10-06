import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useFormPromptPermissions } from './useFormPromptPermissions'

const mockUseCanI = vi.fn()

vi.mock('../../../hooks/useCanI', () => ({
  useCanI: (...args: unknown[]): unknown => mockUseCanI(...args),
}))

describe('useFormPromptPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseCanI.mockImplementation((action: string) => ({
      allowed: true,
      isChecking: false,
      isError: false,
      action,
    }))
  })

  it('returns read and submit when global permissions are granted', () => {
    const { result } = renderHook(() => useFormPromptPermissions('proj-1'))

    expect(result.current.canRead).toBe(true)
    expect(result.current.canSubmit).toBe(true)
    expect(result.current.isChecking).toBe(false)
    expect(result.current.isError).toBe(false)
  })

  it('returns canRead false when read checks deny', () => {
    mockUseCanI.mockImplementation((action: string) => ({
      allowed: action !== 'read',
      isChecking: false,
      isError: false,
    }))

    const { result } = renderHook(() => useFormPromptPermissions())

    expect(result.current.canRead).toBe(false)
    expect(result.current.canSubmit).toBe(true)
  })

  it('aggregates isError from any permission query', () => {
    mockUseCanI.mockImplementation((action: string) => ({
      allowed: true,
      isChecking: false,
      isError: action === 'submit',
    }))

    const { result } = renderHook(() => useFormPromptPermissions('proj-1'))

    expect(result.current.isError).toBe(true)
  })

  it('passes project id to project-scoped checks', async () => {
    renderHook(() => useFormPromptPermissions('proj-abc'))

    await waitFor(() => {
      expect(mockUseCanI).toHaveBeenCalledWith('read', 'form_prompt', { resourceProject: 'proj-abc' })
    })
    expect(mockUseCanI).toHaveBeenCalledWith('submit', 'form_prompt', { resourceProject: 'proj-abc' })
  })
})
