import type { FormsAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import { formsClient } from '../../../client'
import type { ProjectRead } from '../../access/types'

export type FormResponseListRow = FormsAPI.components['schemas']['FormPromptListRead'] & {
  workflowName: string
  workflowId?: string | null
  workflowVersion?: number | null
}

type UseFormResponsesDataParams = {
  projectSelectorReady: boolean
  isAllProjects: boolean
  stableProjectId: string | null | undefined
  queryParams: Record<string, unknown>
  projects: ProjectRead[]
}

export function useFormResponsesData({
  projectSelectorReady,
  isAllProjects,
  queryParams,
  projects,
}: UseFormResponsesDataParams) {
  const formPromptsQuery = formsClient.useQuery(
    'get',
    '/form_prompts',
    {
      params: { query: queryParams },
    },
    {
      enabled: projectSelectorReady,
    }
  )

  const enrichedRows = useMemo((): FormResponseListRow[] => {
    const rows = formPromptsQuery.data?.resources ?? []
    return rows.map((row) => ({
      ...row,
      workflowName: row.workflow_name ?? 'Unknown',
      workflowId: row.workflow_id,
      workflowVersion: row.workflow_version,
    }))
  }, [formPromptsQuery.data?.resources])

  const groupedRows = useMemo(() => {
    if (!isAllProjects) return null
    const groups = new Map<string, { project: (typeof projects)[number] | null; rows: FormResponseListRow[] }>()
    for (const row of enrichedRows) {
      const projectId = row.project_id ?? 'unknown'
      if (!groups.has(projectId)) {
        groups.set(projectId, {
          project: projects.find((p) => p.id === projectId) ?? null,
          rows: [],
        })
      }
      const group = groups.get(projectId)
      if (group) group.rows.push(row)
    }
    return groups
  }, [enrichedRows, projects, isAllProjects])

  return {
    formPromptsQuery,
    enrichedRows,
    groupedRows,
    sortedRows: enrichedRows,
  }
}
