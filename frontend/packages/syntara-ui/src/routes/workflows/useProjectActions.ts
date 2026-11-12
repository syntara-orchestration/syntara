import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import type { useAlerts } from '../../providers/alerts'
import { useProjectStore } from '../../stores/useProjectStore'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { accessClient } from '../access/accessClient'
import type { ProjectRead } from '../access/types'

type UseProjectActionsOptions = {
  showSuccess: ReturnType<typeof useAlerts>['showSuccess']
  showError: ReturnType<typeof useAlerts>['showError']
  onRefetch: () => void
  onDeleteSettled?: () => void
}

export function useProjectActions({ showSuccess, showError, onRefetch, onDeleteSettled }: UseProjectActionsOptions) {
  const queryClient = useQueryClient()
  const { mutate: deleteProject, isPending: isDeletingProject } = accessClient.useMutation(
    'delete',
    '/projects/{project_id}'
  )

  const handleDeleteProject = useCallback(
    (project: ProjectRead) => {
      if (!project?.id) return

      deleteProject(
        { params: { path: { project_id: project.id } } },
        {
          onSuccess: () => {
            showSuccess({
              title: 'Project deleted',
              description: `Project "${project.name}" has been deleted successfully.`,
            })
            detachPromise(queryClient.invalidateQueries({ queryKey: ['all-projects'] }))
            // Deleting the currently selected project would otherwise leave the page
            // querying a now-nonexistent project_id, surfacing a "project not found" error.
            if (useProjectStore.getState().selectedProjectId === project.id) {
              useProjectStore.getState().setSelectedProjectId(null)
            }
            onRefetch()
          },
          onError: (error: unknown) => {
            showError({
              title: 'Delete failed',
              description: `Failed to delete project "${project.name}": ${getErrorMessage(error)}`,
            })
          },
          onSettled: () => {
            onDeleteSettled?.()
          },
        }
      )
    },
    [deleteProject, showSuccess, showError, onRefetch, onDeleteSettled, queryClient]
  )

  return {
    handleDeleteProject,
    isDeletingProject,
  }
}
