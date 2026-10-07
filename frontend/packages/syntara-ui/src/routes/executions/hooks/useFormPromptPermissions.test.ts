import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useFormPromptPermissions } from './useFormPromptPermissions'

const mockUseCanI = vi.fn()
const mockUseAllPermissions = vi.hoisted(() => vi.fn())

vi.mock('../../../hooks/useCanI', () => ({
  useCanI: (...args: unknown[]): unknown => mockUseCanI(...args),
}))

vi.mock('../../access/useAllPermissions', () => ({
  useAllPermissions: mockUseAllPermissions,
}))

describe('useFormPromptPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAllPermissions.mockReturnValue({ permissions: [], isLoading: false, error: null })
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

  it('grants read when project-scoped form_prompt:read is present in all permissions', () => {
    mockUseCanI.mockImplementation(() => ({
      allowed: false,
      isChecking: false,
      isError: false,
    }))
    mockUseAllPermissions.mockReturnValue({
      permissions: [{ effect: 'allow', actions: ['form_prompt:read'], scope: 'project', project: 'Alpha' }],
      isLoading: false,
      error: null,
    })

    const { result } = renderHook(() => useFormPromptPermissions())

    expect(result.current.canRead).toBe(true)
    expect(result.current.tooltips.submit).toContain('form_prompt:submit')
  })

  it('grants submit when a named project has form_prompt:submit in all permissions', () => {
    mockUseCanI.mockImplementation(() => ({
      allowed: false,
      isChecking: false,
      isError: false,
    }))
    mockUseAllPermissions.mockReturnValue({
      permissions: [{ effect: 'allow', actions: ['form_prompt:submit'], scope: 'project', project: 'Beta' }],
      isLoading: false,
      error: null,
    })

    const { result } = renderHook(() => useFormPromptPermissions())
    expect(result.current.canSubmit).toBe(true)
  })

  it('grants submit when project-scoped form_prompt:submit is present in all permissions', () => {
    mockUseCanI.mockImplementation((action: string) => ({
      allowed: action === 'read',
      isChecking: false,
      isError: false,
    }))
    mockUseAllPermissions.mockReturnValue({
      permissions: [{ effect: 'allow', actions: ['form_prompt:submit'], scope: 'system', project: '' }],
      isLoading: false,
      error: null,
    })

    const { result } = renderHook(() => useFormPromptPermissions())
    expect(result.current.canSubmit).toBe(true)
  })

  it('aggregates isChecking when all-permissions is loading', () => {
    mockUseAllPermissions.mockReturnValue({
      permissions: [],
      isLoading: true,
      error: null,
    })

    const { result } = renderHook(() => useFormPromptPermissions())
    expect(result.current.isChecking).toBe(true)
  })

  it('passes project id to project-scoped checks', async () => {
    renderHook(() => useFormPromptPermissions('proj-abc'))

    await waitFor(() => {
      expect(mockUseCanI).toHaveBeenCalledWith('read', 'form_prompt', { resourceProject: 'proj-abc' })
    })
    expect(mockUseCanI).toHaveBeenCalledWith('submit', 'form_prompt', { resourceProject: 'proj-abc' })
  })
})
