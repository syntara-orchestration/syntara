/**
 * Lists workflows that can be embedded into the current workflow (SDP R16).
 *
 * Scope (V1, agreed): same project as the parent, with at least one published version.
 * Unlike Reference mode, Embed does NOT require a Subworkflow Trigger — any published
 * workflow in the project is embeddable. The current workflow is excluded.
 *
 * The project workflow list is cursor-paginated, so we follow `next` to collect every
 * page (bounded by MAX_PAGES) before filtering to published workflows — otherwise
 * published workflows past the first page are unreachable in large projects.
 */
import type { WorkflowAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { accessFetchClient } from '../access/accessClient'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

export type UseEmbeddableWorkflowsResult = {
  workflows: Workflow[]
  isLoading: boolean
  isError: boolean
  error: unknown
}

/** Safety bound on pagination (100 per page ⇒ up to 5000 workflows scanned). */
const MAX_PAGES = 50
const PAGE_SIZE = 100

export function useEmbeddableWorkflows(
  projectId: string | null | undefined,
  currentWorkflowId: string | undefined
): UseEmbeddableWorkflowsResult {
  const query = useQuery({
    queryKey: ['embeddable-workflows', projectId],
    enabled: !!projectId,
    queryFn: async (): Promise<Workflow[]> => {
      const all: Workflow[] = []
      let cursor: string | undefined
      for (let page = 0; page < MAX_PAGES; page += 1) {
        const { data, error } = await accessFetchClient.GET('/projects/{project_id}/workflows', {
          params: {
            path: { project_id: projectId as string },
            query: { limit: PAGE_SIZE, sort: 'name', ...(cursor ? { cursor } : {}) },
          },
        })
        if (error) throw new Error('Failed to load project workflows')
        all.push(...((data?.resources ?? []) as Workflow[]))
        cursor = data?.next ?? undefined
        if (!cursor) break
      }
      return all
    },
  })

  const workflows = useMemo(() => {
    const all = query.data ?? []
    // Published-only (Embed Mode) and never the workflow being edited.
    return all.filter((w) => w.published_version_id != null && w.id !== currentWorkflowId)
  }, [query.data, currentWorkflowId])

  return { workflows, isLoading: query.isLoading, isError: query.isError, error: query.error }
}
