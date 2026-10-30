import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useDeleteAction } from './useDeleteAction'

const mockShowAlert = vi.fn()

vi.mock('../providers/alerts', () => ({
  useAlerts: () => ({ showAlert: mockShowAlert }),
}))

vi.mock('../utils/apiErrors', () => ({
  getErrorMessage: (error: unknown) => String(error),
}))

type TestItem = {
  id: string
  name: string
}

function createTestItem(overrides?: Partial<TestItem>): TestItem {
  return { id: '1', name: 'Test Item', ...overrides }
}

function createDefaultOptions(overrides?: Partial<Parameters<typeof useDeleteAction<TestItem, unknown>>[0]>) {
  return {
    deleteFn: vi.fn(),
    buildParams: vi.fn((item: TestItem) => ({ params: { path: { id: item.id } } })),
    entityLabel: 'credential',
    getItemName: (item: TestItem) => item.name,
    onSuccess: vi.fn(),
    onSettled: vi.fn(),
    ...overrides,
  }
}

describe('useDeleteAction', () => {
  beforeEach(() => {
    mockShowAlert.mockClear()
  })

  it('does nothing when called with null', () => {
    // Arrange
    const options = createDefaultOptions()
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(null)
    })

    // Assert
    expect(options.deleteFn).not.toHaveBeenCalled()
    expect(options.buildParams).not.toHaveBeenCalled()
    expect(mockShowAlert).not.toHaveBeenCalled()
  })

  it('calls deleteFn with buildParams result', () => {
    // Arrange
    const item = createTestItem()
    const expectedParams = { params: { path: { id: '1' } } }
    const options = createDefaultOptions()
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(options.buildParams).toHaveBeenCalledWith(item)
    expect(options.deleteFn).toHaveBeenCalledWith(expectedParams, expect.any(Object))
  })

  it('shows success alert on successful deletion', () => {
    // Arrange
    const item = createTestItem({ name: 'My Credential' })
    const options = createDefaultOptions({
      deleteFn: vi.fn((_params, callbacks: { onSuccess: () => void }) => {
        callbacks.onSuccess()
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(mockShowAlert).toHaveBeenCalledWith({
      title: 'Credential deleted',
      description: 'Credential "My Credential" has been deleted successfully.',
      variant: 'success',
      autoDismiss: true,
    })
  })

  it('calls onSuccess callback on successful deletion', () => {
    // Arrange
    const item = createTestItem()
    const options = createDefaultOptions({
      deleteFn: vi.fn((_params, callbacks: { onSuccess: () => void }) => {
        callbacks.onSuccess()
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(options.onSuccess).toHaveBeenCalledOnce()
  })

  it('shows error alert on failure', () => {
    // Arrange
    const item = createTestItem({ name: 'My Credential' })
    const testError = 'Network error'
    const options = createDefaultOptions({
      deleteFn: vi.fn((_params, callbacks: { onError: (error: unknown) => void }) => {
        callbacks.onError(testError)
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(mockShowAlert).toHaveBeenCalledWith({
      title: 'Delete failed',
      description: 'Failed to delete credential "My Credential": Network error',
      variant: 'error',
      autoDismiss: true,
    })
  })

  it('does not call onSuccess on failure', () => {
    // Arrange
    const item = createTestItem()
    const options = createDefaultOptions({
      deleteFn: vi.fn((_params, callbacks: { onError: (error: unknown) => void }) => {
        callbacks.onError('some error')
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(options.onSuccess).not.toHaveBeenCalled()
  })

  it('calls onSettled on successful deletion', () => {
    // Arrange
    const item = createTestItem()
    const options = createDefaultOptions({
      deleteFn: vi.fn((_params, callbacks: { onSuccess: () => void; onSettled: () => void }) => {
        callbacks.onSuccess()
        callbacks.onSettled()
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(options.onSettled).toHaveBeenCalledOnce()
  })

  it('calls onSettled on failed deletion', () => {
    // Arrange
    const item = createTestItem()
    const options = createDefaultOptions({
      deleteFn: vi.fn((_params, callbacks: { onError: (error: unknown) => void; onSettled: () => void }) => {
        callbacks.onError('error')
        callbacks.onSettled()
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(options.onSettled).toHaveBeenCalledOnce()
  })

  it('capitalizes entityLabel in success alert title', () => {
    // Arrange
    const item = createTestItem()
    const options = createDefaultOptions({
      entityLabel: 'user',
      deleteFn: vi.fn((_params, callbacks: { onSuccess: () => void }) => {
        callbacks.onSuccess()
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'User deleted',
      })
    )
    const alertCall = mockShowAlert.mock.calls[0]?.[0] as { description: string }
    expect(alertCall.description).toContain('User "Test Item"')
  })

  it('capitalizes entityLabel in error alert description', () => {
    // Arrange
    const item = createTestItem({ name: 'admin' })
    const options = createDefaultOptions({
      entityLabel: 'group',
      deleteFn: vi.fn((_params, callbacks: { onError: (error: unknown) => void }) => {
        callbacks.onError('forbidden')
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'Failed to delete group "admin": forbidden',
      })
    )
  })

  it('uses custom successTitle when provided', () => {
    // Arrange
    const item = createTestItem()
    const options = createDefaultOptions({
      successTitle: 'Item removed',
      deleteFn: vi.fn((_params, callbacks: { onSuccess: () => void }) => {
        callbacks.onSuccess()
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Item removed',
      })
    )
  })

  it('uses custom successDescription when provided', () => {
    // Arrange
    const item = createTestItem({ name: 'Staging OpenShift' })
    const options = createDefaultOptions({
      successTitle: 'Deletion accepted',
      successDescription: (itemName) =>
        `Execution target "${itemName}" deletion was accepted; it may remain listed briefly while draining completes.`,
      deleteFn: vi.fn((_params, callbacks: { onSuccess: () => void }) => {
        callbacks.onSuccess()
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(mockShowAlert).toHaveBeenCalledWith({
      title: 'Deletion accepted',
      description:
        'Execution target "Staging OpenShift" deletion was accepted; it may remain listed briefly while draining completes.',
      variant: 'success',
      autoDismiss: true,
    })
  })

  it('uses custom errorTitle when provided', () => {
    // Arrange
    const item = createTestItem()
    const options = createDefaultOptions({
      errorTitle: 'Removal failed',
      deleteFn: vi.fn((_params, callbacks: { onError: (error: unknown) => void }) => {
        callbacks.onError('error')
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Removal failed',
      })
    )
  })

  it('works without optional onSuccess and onSettled callbacks', () => {
    // Arrange
    const item = createTestItem()
    const options = createDefaultOptions({
      onSuccess: undefined,
      onSettled: undefined,
      deleteFn: vi.fn(
        (_params, callbacks: { onSuccess: () => void; onError: (error: unknown) => void; onSettled: () => void }) => {
          callbacks.onSuccess()
          callbacks.onSettled()
        }
      ),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act & Assert - should not throw
    act(() => {
      result.current(item)
    })

    expect(mockShowAlert).toHaveBeenCalledWith(expect.objectContaining({ variant: 'success' }))
  })

  it('returns a stable function reference across re-renders with same options', () => {
    // Arrange
    const options = createDefaultOptions()
    const { result, rerender } = renderHook(() => useDeleteAction(options))
    const firstRef = result.current

    // Act
    rerender()

    // Assert
    expect(result.current).toBe(firstRef)
  })

  it('uses getItemName to extract the display name for alerts', () => {
    // Arrange
    const item = createTestItem({ id: '42', name: 'Production Workflow' })
    const options = createDefaultOptions({
      getItemName: (i: TestItem) => `custom-${i.id}`,
      deleteFn: vi.fn((_params, callbacks: { onSuccess: () => void }) => {
        callbacks.onSuccess()
      }),
    })
    const { result } = renderHook(() => useDeleteAction(options))

    // Act
    act(() => {
      result.current(item)
    })

    // Assert
    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'Credential "custom-42" has been deleted successfully.',
      })
    )
  })
})
