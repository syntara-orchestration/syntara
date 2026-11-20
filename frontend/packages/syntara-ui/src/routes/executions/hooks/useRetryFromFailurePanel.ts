import type { useNavigate } from '@tanstack/react-router'
import { useRef, useState } from 'react'

import { detachPromise } from '../../../utils/detachPromise'

type UseRetryFromFailurePanelParams = Readonly<{
  navigate: ReturnType<typeof useNavigate>
  executionId: string
  historyCardOpen: boolean
  closeApprovalPanel: () => void
}>

/** Owns the retry review panel lifecycle and restores focus to its opener on close. */
export function useRetryFromFailurePanel({
  navigate,
  executionId,
  historyCardOpen,
  closeApprovalPanel,
}: UseRetryFromFailurePanelParams) {
  const [isOpen, setIsOpen] = useState(false)
  const triggerRef = useRef<HTMLElement | null>(null)

  const open = (trigger: HTMLElement) => {
    triggerRef.current = trigger
    closeApprovalPanel()
    if (historyCardOpen) {
      detachPromise(
        navigate({
          to: '/executions/$executionId',
          params: { executionId },
          search: (prev: Record<string, unknown>) => ({ ...prev, history: 'closed' }),
        })
      )
    }
    setIsOpen(true)
  }

  const close = () => {
    setIsOpen(false)
    requestAnimationFrame(() => {
      const trigger = triggerRef.current
      triggerRef.current = null
      const focusTarget = trigger?.isConnected
        ? trigger
        : document.querySelector<HTMLElement>(
            '[data-testid="retry-run-menu-toggle"], [data-testid="retry-from-failure-button"]'
          )
      focusTarget?.focus()
    })
  }

  const closeWithoutFocus = () => {
    triggerRef.current = null
    setIsOpen(false)
  }

  return { isOpen, open, close, closeWithoutFocus }
}
