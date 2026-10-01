import type { FormsAPI } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import { formsFetchClient } from '../../../client'

type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']
type ListQuery = NonNullable<FormsAPI.operations['list_form_prompts']['parameters']['query']>

const PAGE_SIZE = 100

function isValidFormPromptSummary(item: unknown): item is FormPromptSummary {
  if (typeof item !== 'object' || item === null) return false
  const record = item as Record<string, unknown>
  return (
    typeof record.id === 'string' &&
    typeof record.prompt_node_id === 'string' &&
    typeof record.execution_id === 'string'
  )
}

async function listFormPromptsForExecution(
  executionId: string,
  filters?: Pick<ListQuery, 'status'>
): Promise<FormPromptSummary[]> {
  const normalizedExecutionId = executionId.toLowerCase()
  const collected: FormPromptSummary[] = []
  let cursor: string | null | undefined

  for (;;) {
    const query: ListQuery = {
      execution_id: executionId,
      limit: PAGE_SIZE,
      ...(cursor ? { cursor } : {}),
      ...filters,
    }

    const { data, error, response } = await formsFetchClient.GET('/form_prompts', {
      params: { query },
    })

    if (error || !response.ok) {
      const message = error instanceof Error ? error.message : `Failed to list form prompts (${response.status})`
      throw new Error(message)
    }

    const page = (data?.resources ?? [])
      .filter(isValidFormPromptSummary)
      .filter((prompt) => prompt.execution_id.toLowerCase() === normalizedExecutionId)
      .map((prompt) => ({
        ...prompt,
        project_id: typeof prompt.project_id === 'string' ? prompt.project_id : '',
        name: typeof prompt.name === 'string' ? prompt.name : prompt.prompt_node_id,
        status: prompt.status ?? 'pending',
        temporal_activity_id: typeof prompt.temporal_activity_id === 'string' ? prompt.temporal_activity_id : '',
      }))
    collected.push(...page)

    cursor = data?.next
    if (!cursor) break
  }

  return collected
}

type UseFetchFormPromptsForExecutionResult = {
  isLoading: boolean
  fetchPendingFormPrompts: () => Promise<FormPromptSummary[]>
  fetchFormPromptsForExecution: () => Promise<FormPromptSummary[]>
  clear: () => void
}

/**
 * Lazily fetches form prompts for an execution (on canvas click or auto-detect).
 * Uses openapi-fetch directly so on-demand loads always hit the network.
 */
export function useFetchFormPromptsForExecution(executionId: string): UseFetchFormPromptsForExecutionResult {
  const [isLoading, setIsLoading] = useState(false)

  const fetchPendingFormPrompts = useCallback(async (): Promise<FormPromptSummary[]> => {
    if (!executionId) return []
    setIsLoading(true)
    try {
      return await listFormPromptsForExecution(executionId, { status: 'pending' })
    } finally {
      setIsLoading(false)
    }
  }, [executionId])

  const fetchFormPromptsForExecution = useCallback(async (): Promise<FormPromptSummary[]> => {
    if (!executionId) return []
    setIsLoading(true)
    try {
      return await listFormPromptsForExecution(executionId)
    } finally {
      setIsLoading(false)
    }
  }, [executionId])

  const clear = useCallback(() => {
    setIsLoading(false)
  }, [])

  return { isLoading, fetchPendingFormPrompts, fetchFormPromptsForExecution, clear }
}
