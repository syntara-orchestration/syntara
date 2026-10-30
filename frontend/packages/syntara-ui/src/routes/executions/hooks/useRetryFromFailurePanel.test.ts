import type { useNavigate } from '@tanstack/react-router'
import { act, renderHook, waitFor } from '@testing-library/react'

import { useRetryFromFailurePanel } from './useRetryFromFailurePanel'

describe('useRetryFromFailurePanel', () => {
  it('opens the panel and restores focus to its trigger on close', async () => {
    const navigate = vi.fn() as unknown as ReturnType<typeof useNavigate>
    const closeApprovalPanel = vi.fn()
    const trigger = document.createElement('button')
    document.body.append(trigger)
    const { result } = renderHook(() =>
      useRetryFromFailurePanel({
        navigate,
        executionId: 'exec-123',
        historyCardOpen: false,
        closeApprovalPanel,
      })
    )

    act(() => result.current.open(trigger))

    expect(result.current.isOpen).toBe(true)
    expect(closeApprovalPanel).toHaveBeenCalledOnce()
    const otherControl = document.createElement('button')
    document.body.append(otherControl)
    otherControl.focus()

    act(() => result.current.close())

    expect(result.current.isOpen).toBe(false)
    await waitFor(() => expect(trigger).toHaveFocus())
    trigger.remove()
    otherControl.remove()
  })

  it('closes the history panel before opening retry review', () => {
    const navigate = vi.fn() as unknown as ReturnType<typeof useNavigate>
    const { result } = renderHook(() =>
      useRetryFromFailurePanel({
        navigate,
        executionId: 'exec-123',
        historyCardOpen: true,
        closeApprovalPanel: vi.fn(),
      })
    )

    act(() => result.current.open(document.createElement('button')))

    expect(navigate).toHaveBeenCalledWith({
      to: '/executions/$executionId',
      params: { executionId: 'exec-123' },
      search: expect.any(Function) as unknown,
    })
    expect(result.current.isOpen).toBe(true)
  })

  it('closes without restoring focus when another panel replaces it', () => {
    const navigate = vi.fn() as unknown as ReturnType<typeof useNavigate>
    const trigger = document.createElement('button')
    const otherControl = document.createElement('button')
    document.body.append(trigger, otherControl)
    const { result } = renderHook(() =>
      useRetryFromFailurePanel({
        navigate,
        executionId: 'exec-123',
        historyCardOpen: false,
        closeApprovalPanel: vi.fn(),
      })
    )

    act(() => result.current.open(trigger))
    otherControl.focus()
    act(() => result.current.closeWithoutFocus())

    expect(result.current.isOpen).toBe(false)
    expect(otherControl).toHaveFocus()
    trigger.remove()
    otherControl.remove()
  })
})
