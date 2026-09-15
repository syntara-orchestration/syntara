import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { useAuthStore } from '../../../stores/useAuthStore'
import { accessClient } from '../../access/accessClient'
import { logoutWithAlert } from '../logoutWithAlert'
import { COMPLIANT_TEST_PASSWORD } from '../passwordComplexity.testFixtures'
import type { UserFormData } from '../userFormSchema'

import { useUserFormSubmit } from './useUserFormSubmit'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/accessClient', () => ({
  accessClient: { useMutation: vi.fn() },
}))

vi.mock('../../../hooks/useFormMutationErrorHandler', () => ({
  useFormMutationErrorHandler: vi.fn(),
}))

vi.mock('../../../stores/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}))

vi.mock('../logoutWithAlert', () => ({
  logoutWithAlert: vi.fn(),
}))

const mockShowAlert = vi.fn()

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showAlert: mockShowAlert }),
}))

const mockCreateMutate = vi.fn()
const mockUpdateMutate = vi.fn()
const mockLogout = vi.fn().mockResolvedValue(undefined)
const mockErrorHandler = vi.fn().mockReturnValue(vi.fn())
const mockNavigateBack = vi.fn()
const mockSetError = vi.fn()

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupMocks() {
  let callIndex = 0
  vi.mocked(accessClient.useMutation).mockImplementation(() => {
    const result =
      callIndex === 0 ? { mutate: mockCreateMutate, isPending: false } : { mutate: mockUpdateMutate, isPending: false }
    callIndex++
    return result as never
  })
  vi.mocked(useFormMutationErrorHandler).mockReturnValue(mockErrorHandler)
  vi.mocked(useAuthStore).mockImplementation((selector: unknown) =>
    (selector as (s: { logout: () => Promise<void> }) => unknown)({
      logout: mockLogout,
    })
  )
}

const baseFormData: UserFormData = {
  username: 'testuser',
  first_name: 'Test',
  last_name: 'User',
  email: 'test@example.com',
  password: '',
  is_enabled: true,
  group_names: [],
}

const defaultOptions = {
  isEdit: true,
  isValidId: true,
  userId: 'user-123',
  isBuiltinUser: false,
  isFederatedUser: false,
  isSelf: false,
  setError: mockSetError,
  navigateBack: mockNavigateBack,
}

function getOnSuccess(): () => void {
  const callbacks = mockUpdateMutate.mock.calls[0][1] as {
    onSuccess: () => void
  }
  return callbacks.onSuccess
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useUserFormSubmit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupMocks()
  })

  describe('edit mode — standard update', () => {
    it('calls updateUser with correct params on edit submit', () => {
      const { result } = renderHook(() => useUserFormSubmit(defaultOptions))

      act(() => {
        result.current.onSubmit(baseFormData)
      })

      expect(mockUpdateMutate).toHaveBeenCalledTimes(1)
      expect(mockUpdateMutate.mock.calls[0][0]).toEqual({
        params: { path: { user_id: 'user-123' } },
        body: {
          username: 'testuser',
          first_name: 'Test',
          last_name: 'User',
          email: 'test@example.com',
        },
      })
    })

    it('shows success alert and navigates back on update success', () => {
      const { result } = renderHook(() => useUserFormSubmit(defaultOptions))

      act(() => {
        result.current.onSubmit(baseFormData)
      })
      act(() => {
        getOnSuccess()()
      })

      expect(mockShowAlert).toHaveBeenCalledWith({
        title: 'User updated',
        variant: 'success',
        autoDismiss: true,
      })
      expect(mockNavigateBack).toHaveBeenCalled()
      expect(logoutWithAlert).not.toHaveBeenCalled()
    })

    it('omits is_enabled from the edit PATCH body', () => {
      const { result } = renderHook(() => useUserFormSubmit(defaultOptions))

      act(() => {
        result.current.onSubmit({ ...baseFormData, is_enabled: false })
      })

      const patchArgs = mockUpdateMutate.mock.calls[0][0] as {
        body: Record<string, unknown>
      }
      expect(patchArgs.body).not.toHaveProperty('is_enabled')
    })
  })

  describe('edit mode — password change', () => {
    it('calls logoutWithAlert when self changes password', () => {
      const { result } = renderHook(() => useUserFormSubmit({ ...defaultOptions, isSelf: true }))

      act(() => {
        result.current.onSubmit({ ...baseFormData, password: COMPLIANT_TEST_PASSWORD })
      })
      act(() => {
        getOnSuccess()()
      })

      expect(logoutWithAlert).toHaveBeenCalledWith(mockLogout, mockShowAlert, 'Password changed — signing out')
      expect(mockNavigateBack).not.toHaveBeenCalled()
    })

    it('shows alert and navigates back when non-self changes password', () => {
      const { result } = renderHook(() => useUserFormSubmit({ ...defaultOptions, isSelf: false }))

      act(() => {
        result.current.onSubmit({ ...baseFormData, password: COMPLIANT_TEST_PASSWORD })
      })
      act(() => {
        getOnSuccess()()
      })

      expect(mockShowAlert).toHaveBeenCalledWith({
        title: 'User updated',
        description: 'Password changed — all active sessions for this user have been revoked.',
        variant: 'success',
        autoDismiss: true,
      })
      expect(mockNavigateBack).toHaveBeenCalled()
      expect(logoutWithAlert).not.toHaveBeenCalled()
    })
  })

  describe('create mode', () => {
    it('sends null first_name when the field is blank', () => {
      const { result } = renderHook(() => useUserFormSubmit({ ...defaultOptions, isEdit: false }))

      act(() => {
        result.current.onSubmit({
          ...baseFormData,
          first_name: '',
          last_name: '',
          password: COMPLIANT_TEST_PASSWORD,
        })
      })

      expect(mockCreateMutate).toHaveBeenCalledTimes(1)
      expect(mockCreateMutate.mock.calls[0][0]).toEqual({
        body: {
          username: 'testuser',
          email: 'test@example.com',
          first_name: null,
          last_name: null,
          password: COMPLIANT_TEST_PASSWORD,
          is_enabled: true,
          group_names: [],
        },
      })
    })

    it('calls createUser and shows success on create', () => {
      const { result } = renderHook(() => useUserFormSubmit({ ...defaultOptions, isEdit: false }))

      act(() => {
        result.current.onSubmit({ ...baseFormData, password: COMPLIANT_TEST_PASSWORD })
      })

      expect(mockCreateMutate).toHaveBeenCalledTimes(1)
      const createArgs = mockCreateMutate.mock.calls[0][0] as {
        body: { first_name: string | null }
      }
      expect(createArgs.body.first_name).toBe('Test')

      const callbacks = mockCreateMutate.mock.calls[0][1] as { onSuccess: () => void }
      act(() => {
        callbacks.onSuccess()
      })

      expect(mockShowAlert).toHaveBeenCalledWith({
        title: 'User created',
        variant: 'success',
        autoDismiss: true,
      })
      expect(mockNavigateBack).toHaveBeenCalled()
    })
  })

  describe('error handling', () => {
    it('passes error handler to updateUser onError', () => {
      const { result } = renderHook(() => useUserFormSubmit(defaultOptions))

      act(() => {
        result.current.onSubmit(baseFormData)
      })

      expect(mockUpdateMutate).toHaveBeenCalledTimes(1)
      expect(mockErrorHandler).toHaveBeenCalledWith({
        title: 'Failed to update user',
        context: 'User "testuser"',
      })
    })
  })

  describe('builtin user handling', () => {
    it('omits username, first_name, and last_name for builtin users', () => {
      const { result } = renderHook(() => useUserFormSubmit({ ...defaultOptions, isBuiltinUser: true }))

      act(() => {
        result.current.onSubmit(baseFormData)
      })

      const callArg = mockUpdateMutate.mock.calls[0][0] as {
        body: Record<string, unknown>
      }
      expect(callArg.body).toEqual({})
    })
  })

  describe('isSaving state', () => {
    it('returns isSaving false when neither mutation is pending', () => {
      const { result } = renderHook(() => useUserFormSubmit(defaultOptions))
      expect(result.current.isSaving).toBe(false)
    })
  })
})
