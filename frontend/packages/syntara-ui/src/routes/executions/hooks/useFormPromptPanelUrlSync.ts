import type { FormsAPI } from '@syntara/contracts'
import { useEffect, type RefObject } from 'react'

import type { FormPromptUrlLookupState } from './useFetchFormPromptForUrlParam'

type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']

type UseFormPromptPanelUrlSyncOptions = {
  executionId: string | undefined
  formPromptIdFromUrl: string | null
  urlFormPromptLookup: FormPromptUrlLookupState
  urlFormPrompt: FormsAPI.components['schemas']['FormPromptRead'] | undefined
  handledUrlPromptIdRef: RefObject<string | null>
  fetchPendingFormPrompts: () => Promise<FormPromptSummary[]>
  setFormPromptsAndIndex: (prompts: FormPromptSummary[], index: number) => void
  setPanelOpen: (open: boolean) => void
  showError: (alert: { title: string; description: string }) => void
}

export function useFormPromptPanelUrlSync({
  executionId,
  formPromptIdFromUrl,
  urlFormPromptLookup,
  urlFormPrompt,
  handledUrlPromptIdRef,
  fetchPendingFormPrompts,
  setFormPromptsAndIndex,
  setPanelOpen,
  showError,
}: UseFormPromptPanelUrlSyncOptions): void {
  useEffect(() => {
    if (!formPromptIdFromUrl) {
      handledUrlPromptIdRef.current = null
      return
    }
    if (urlFormPromptLookup.isLoading) {
      return
    }
    if (urlFormPromptLookup.isError) {
      if (handledUrlPromptIdRef.current === formPromptIdFromUrl) {
        return
      }
      handledUrlPromptIdRef.current = formPromptIdFromUrl
      showError({
        title: 'Failed to load form prompt',
        description: 'Could not load the linked form prompt. Check the URL or try again.',
      })
      return
    }
    if (!urlFormPrompt?.id || urlFormPrompt.id === handledUrlPromptIdRef.current) {
      return
    }

    handledUrlPromptIdRef.current = urlFormPrompt.id
    let cancelled = false

    const promptExecutionId = urlFormPrompt.execution_id?.toLowerCase()
    const routeExecutionId = executionId?.toLowerCase()
    if (promptExecutionId && routeExecutionId && promptExecutionId !== routeExecutionId) {
      showError({
        title: 'Form prompt unavailable',
        description: 'This form prompt link belongs to a different workflow run.',
      })
      handledUrlPromptIdRef.current = null
      return
    }

    fetchPendingFormPrompts()
      .then((fetched) => {
        if (cancelled) return
        const index = fetched.findIndex((p) => p.id === urlFormPrompt.id)
        if (index >= 0) {
          setFormPromptsAndIndex(fetched, index)
        } else if (urlFormPrompt.prompt_node_id) {
          setFormPromptsAndIndex(
            [
              {
                id: urlFormPrompt.id ?? '',
                execution_id: urlFormPrompt.execution_id ?? executionId ?? '',
                project_id: urlFormPrompt.project_id ?? '',
                prompt_node_id: urlFormPrompt.prompt_node_id,
                name: urlFormPrompt.name ?? '',
                status: urlFormPrompt.status ?? 'pending',
                loop_iteration_path: urlFormPrompt.loop_iteration_path ?? [],
                temporal_activity_id: '',
              },
            ],
            0
          )
        }
        setPanelOpen(true)
      })
      .catch(() => {
        if (cancelled) return
        handledUrlPromptIdRef.current = null
        showError({
          title: 'Failed to load form prompt',
          description: 'Could not fetch form prompt details. Please try again.',
        })
      })

    return () => {
      cancelled = true
    }
  }, [
    formPromptIdFromUrl,
    urlFormPrompt,
    urlFormPromptLookup.isLoading,
    urlFormPromptLookup.isError,
    fetchPendingFormPrompts,
    setFormPromptsAndIndex,
    showError,
    executionId,
    handledUrlPromptIdRef,
    setPanelOpen,
  ])

  useEffect(() => {
    handledUrlPromptIdRef.current = null
  }, [executionId, handledUrlPromptIdRef])
}
