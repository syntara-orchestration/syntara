import { useNavigate } from '@tanstack/react-router'
import { useCallback } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { detachPromise } from '../../utils/detachPromise'
import type { ProjectRead } from '../access/types'

/**
 * Handler for the Workflows page "Create workflow" actions.
 *
 * Opens the new-workflow page with the project in view pre-filled in its project
 * picker (R18). Built-in projects cannot hold workflows and "All projects" has no
 * single project, so both open the picker empty.
 */
export function useCreateWorkflowNavigation(
  selectedProject: ProjectRead | null,
  stableProjectId: string | undefined
): () => void {
  const navigate = useNavigate()
  const projectId = selectedProject?.is_builtin ? undefined : (selectedProject?.id ?? stableProjectId)
  return useCallback(
    () => detachPromise(navigate({ to: AppRoute.WorkflowBuilder.New, search: projectId ? { projectId } : {} })),
    [navigate, projectId]
  )
}
