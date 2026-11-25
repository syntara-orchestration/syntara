import { ApprovalsAPI } from '@syntara/contracts'
import { keepPreviousData } from '@tanstack/react-query'
import { useMemo } from 'react'

import { approvalsClient } from '../../client'
import { accessClient } from '../access/accessClient'
import type { ProjectRead } from '../access/types'

import type { ApprovalWithDetails } from './Approvals'
import { createApprovalsListPlaceholderData, stripStaleListPaginationCursors } from './approvalsListPlaceholderData'

const getApprovalDetails = (approval: ApprovalWithDetails) => {
  const wfCtx = approval.workflow_context as
    { workflow_name?: string; workflow_id?: string; workflow_version?: number } | undefined
  return {
    approvalName: approval.name || approval.id,
    workflowName: wfCtx?.workflow_name || 'Unknown',
    workflowId: wfCtx?.workflow_id,
    workflowVersion: wfCtx?.workflow_version,
  }
}

type ApprovalsListPageData = ApprovalsAPI.paths['/approvals']['get']['responses'][200]['content']['application/json']

type UseApprovalsDataParams = {
  projectSelectorReady: boolean
  isAllProjects: boolean
  stableProjectId: string | null | undefined
  queryParams: Record<string, unknown>
  projects: ProjectRead[]
}

export function useApprovalsData({
  projectSelectorReady,
  isAllProjects,
  stableProjectId,
  queryParams,
  projects,
}: UseApprovalsDataParams) {
  const allProjectsPlaceholderData = useMemo(
    () => createApprovalsListPlaceholderData<ApprovalsListPageData>('all') as typeof keepPreviousData,
    []
  )
  const projectListScopeKey = `project:${stableProjectId ?? ''}`
  const projectPlaceholderData = useMemo(
    () => createApprovalsListPlaceholderData<ApprovalsListPageData>(projectListScopeKey) as typeof keepPreviousData,
    [projectListScopeKey]
  )

  const allApprovalsQuery = approvalsClient.useQuery(
    'get',
    '/approvals',
    {
      params: { query: queryParams },
    },
    {
      // Keep the table mounted while sort/filter/cursor params change so column header focus is not lost.
      placeholderData: allProjectsPlaceholderData,
      enabled: projectSelectorReady && isAllProjects,
    }
  )

  const projectApprovalsQuery = accessClient.useQuery(
    'get',
    '/projects/{project_id}/approvals',
    {
      params: {
        path: { project_id: stableProjectId ?? '' },
        query: queryParams,
      },
    },
    {
      placeholderData: projectPlaceholderData,
      enabled: !!stableProjectId && !isAllProjects,
    }
  )

  const approvalsQuery = isAllProjects ? allApprovalsQuery : projectApprovalsQuery
  const approvalsData = approvalsQuery.data

  const listDataForPagination = useMemo(
    () => stripStaleListPaginationCursors(approvalsData, approvalsQuery.isPlaceholderData),
    [approvalsData, approvalsQuery.isPlaceholderData]
  )

  const enrichedApprovals = useMemo(() => {
    const approvals = (approvalsData?.resources ?? []) as ApprovalWithDetails[]
    return approvals.map((approval) => {
      const { approvalName, workflowName, workflowId, workflowVersion } = getApprovalDetails(approval)
      return {
        ...approval,
        approvalName,
        workflowName,
        workflowId,
        workflowVersion,
      }
    })
  }, [approvalsData?.resources])

  // Group approvals by project when viewing all projects
  const groupedApprovals = useMemo(() => {
    if (!isAllProjects) return null
    const groups = new Map<string, { project: (typeof projects)[number] | null; approvals: ApprovalWithDetails[] }>()
    for (const approval of enrichedApprovals) {
      const projectId = (approval as unknown as { project_id?: string }).project_id ?? 'unknown'
      if (!groups.has(projectId)) {
        groups.set(projectId, {
          project: projects.find((p) => p.id === projectId) ?? null,
          approvals: [],
        })
      }
      const group = groups.get(projectId)
      if (group) group.approvals.push(approval)
    }
    return groups
  }, [enrichedApprovals, projects, isAllProjects])

  // API order from queryParams.sort — no client-side re-sort
  const sortedApprovals = enrichedApprovals

  return {
    approvalsQuery,
    listDataForPagination,
    enrichedApprovals,
    groupedApprovals,
    sortedApprovals,
  }
}
