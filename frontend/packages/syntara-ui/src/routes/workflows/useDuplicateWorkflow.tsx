import { AlertActionLink } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import { workflowFetchClient } from '../../client'
import type { useAlerts } from '../../providers/alerts'
import { getErrorMessage } from '../../utils/apiErrors'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']
type WorkflowDefinitionSchema = WorkflowAPI.components['schemas']['WorkflowDefinition']

type UseDuplicateWorkflowOptions = {
  showAlert: ReturnType<typeof useAlerts>['showAlert']
  showError: ReturnType<typeof useAlerts>['showError']
  setLocation: (path: string) => void
  onSuccess: () => void
}

/**
 * Hook for duplicating workflows.
 *
 * Fetches the full workflow definition, transforms approval node approver references from
 * object summaries to string arrays (as required by the workflow schema), generates a
 * unique name with timestamp suffix, creates the duplicate via POST /workflows, and
 * navigates to the builder page for the new workflow.
 *
 * @param options - Configuration including alert handlers, navigation, and refetch callback
 * @returns Object with duplicateWorkflow async function and isDuplicating loading state
 */
export function useDuplicateWorkflow({ showAlert, showError, setLocation, onSuccess }: UseDuplicateWorkflowOptions) {
  const [isDuplicating, setIsDuplicating] = useState(false)

  const duplicateWorkflow = useCallback(
    async (workflow: Workflow) => {
      if (!workflow.id || isDuplicating) return
      setIsDuplicating(true)
      try {
        const { data: fullWorkflow, error: fetchError } = await workflowFetchClient.GET('/workflows/{workflow_id}', {
          params: { path: { workflow_id: workflow.id } },
        })
        if (fetchError || !fullWorkflow) {
          showError({ title: 'Failed to duplicate workflow', description: getErrorMessage(fetchError) })
          return
        }

        const definition = fullWorkflow.version?.workflow_definition as Record<string, unknown> | undefined
        if (!definition) {
          showError({ title: 'Failed to duplicate workflow', description: 'Workflow has no definition to duplicate' })
          return
        }

        // Transform approval nodes: convert approver_users/approver_groups from objects to string arrays
        // The API returns {id, username}/{id, name} objects but the workflow schema expects string arrays
        const nodes = definition.nodes as Array<Record<string, unknown>> | undefined
        const transformedDefinition = {
          ...definition,
          nodes: nodes?.map((node) => {
            if (node.type === 'approval' && node.config) {
              const config = node.config as Record<string, unknown>
              const transformedConfig: Record<string, unknown> = { ...config }

              // Extract usernames from ApproverUserSummary[] -> string[]
              if (config.approver_users && Array.isArray(config.approver_users)) {
                transformedConfig.approver_users = config.approver_users.map((u: unknown) =>
                  typeof u === 'object' && u !== null && 'username' in u
                    ? (u as { username: string }).username
                    : String(u)
                )
              }

              // Extract group names from ApproverGroupSummary[] -> string[]
              if (config.approver_groups && Array.isArray(config.approver_groups)) {
                transformedConfig.approver_groups = config.approver_groups.map((g: unknown) =>
                  typeof g === 'object' && g !== null && 'name' in g ? (g as { name: string }).name : String(g)
                )
              }

              return {
                ...node,
                config: transformedConfig,
              }
            }
            return node
          }),
        }

        if (!workflow.project_id) {
          showError({ title: 'Failed to duplicate workflow', description: 'Workflow must have a project ID' })
          return
        }

        const timestamp = Date.now().toString(36)
        const duplicateName = `${workflow.name ?? 'workflow'} - duplicate-${timestamp}`

        const { data: createdWorkflow, error: createError } = await workflowFetchClient.POST('/workflows', {
          body: {
            name: duplicateName,
            description: workflow.description ?? '',
            workflow_definition: transformedDefinition as unknown as WorkflowDefinitionSchema,
            labels: (workflow.labels as Record<string, string> | undefined) ?? {},
            project_id: workflow.project_id,
          },
        })

        if (createError) {
          showError({ title: 'Failed to duplicate workflow', description: getErrorMessage(createError) })
          return
        }

        showAlert({
          variant: 'success',
          autoDismiss: true,
          title: 'Workflow duplicated',
          description: `Created "${duplicateName}"`,
          actionLinks: createdWorkflow?.id ? (
            <AlertActionLink onClick={() => setLocation(`/workflow-builder/${createdWorkflow.id}`)}>
              Open workflow
            </AlertActionLink>
          ) : undefined,
        })
        onSuccess()
      } catch (err: unknown) {
        showError({ title: 'Failed to duplicate workflow', description: getErrorMessage(err) })
      } finally {
        setIsDuplicating(false)
      }
    },
    [isDuplicating, setLocation, showAlert, showError, onSuccess]
  )

  return { duplicateWorkflow, isDuplicating }
}
