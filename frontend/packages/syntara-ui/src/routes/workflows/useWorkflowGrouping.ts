import type { WorkflowAPI } from '@syntara/contracts'
import { useMemo, useState } from 'react'

import type { ProjectRead } from '../access/types'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

export function useWorkflowGrouping(workflows: Workflow[], projects: ProjectRead[], isAllProjects: boolean) {
  const builtinProjectIds = useMemo(() => new Set(projects.filter((p) => p.is_builtin).map((p) => p.id)), [projects])
  const sortedWorkflows = useMemo(() => {
    if (!isAllProjects) return workflows
    return workflows.filter((w) => !builtinProjectIds.has(w.project_id))
  }, [workflows, isAllProjects, builtinProjectIds])

  const [collapsedProjects, setCollapsedProjects] = useState<Set<string>>(new Set())
  const groupedWorkflows = useMemo(() => {
    if (!isAllProjects) return null
    const groups = new Map<string, { project: ProjectRead | null; workflows: Workflow[] }>()
    for (const workflow of sortedWorkflows) {
      const projectId = workflow.project_id
      let group = groups.get(projectId)
      if (group == null) {
        group = { project: projects.find((p) => p.id === projectId) ?? null, workflows: [] }
        groups.set(projectId, group)
      }
      group.workflows.push(workflow)
    }
    return groups
  }, [sortedWorkflows, projects, isAllProjects])

  const toggleProjectCollapsed = (projectId: string) =>
    setCollapsedProjects((prev) =>
      prev.has(projectId) ? new Set([...prev].filter((id) => id !== projectId)) : new Set([...prev, projectId])
    )

  return { sortedWorkflows, groupedWorkflows, collapsedProjects, toggleProjectCollapsed }
}
