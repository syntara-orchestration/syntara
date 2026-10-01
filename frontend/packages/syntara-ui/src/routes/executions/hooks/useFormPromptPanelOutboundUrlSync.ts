import type { NavigateFn } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'

import { detachPromise } from '../../../utils/detachPromise'

/* eslint-disable reactYouMightNotNeedAnEffect/no-event-handler -- TanStack Router search params must track panel open state */

type UseFormPromptPanelOutboundUrlSyncOptions = Readonly<{
  executionId: string | undefined
  panelOpen: boolean
  selectedFormPromptId: string | undefined
  formPromptIdFromUrl: string | null
  navigate: NavigateFn
}>

/**
 * Keeps `?form_prompt=` aligned with panel visibility only.
 * Prev/next navigation inside the panel does not rewrite the URL (avoids refetch loops).
 */
export function useFormPromptPanelOutboundUrlSync({
  executionId,
  panelOpen,
  selectedFormPromptId,
  formPromptIdFromUrl,
  navigate,
}: UseFormPromptPanelOutboundUrlSyncOptions): void {
  const prevPanelOpenRef = useRef(panelOpen)

  useEffect(() => {
    const wasOpen = prevPanelOpenRef.current
    prevPanelOpenRef.current = panelOpen

    if (!executionId) {
      return
    }

    if (wasOpen && !panelOpen && formPromptIdFromUrl) {
      detachPromise(
        navigate({
          to: '/executions/$executionId',
          params: { executionId },
          search: (prev: Record<string, unknown>) => {
            const next = { ...prev }
            delete next.form_prompt
            return next
          },
        })
      )
      return
    }

    if (!wasOpen && panelOpen && selectedFormPromptId && !formPromptIdFromUrl) {
      detachPromise(
        navigate({
          to: '/executions/$executionId',
          params: { executionId },
          search: (prev: Record<string, unknown>) => ({ ...prev, form_prompt: selectedFormPromptId }),
        })
      )
    }
  }, [executionId, panelOpen, selectedFormPromptId, formPromptIdFromUrl, navigate])
}
/* eslint-enable reactYouMightNotNeedAnEffect/no-event-handler */
