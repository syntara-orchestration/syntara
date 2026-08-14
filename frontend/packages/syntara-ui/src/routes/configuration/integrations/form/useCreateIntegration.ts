import { IntegrationTypeEnum, type IntegrationsAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { AppRoute } from '../../../../app/AppRoute'
import { tanstackRouter } from '../../../../app/tanstackRouter'
import { integrationsClient } from '../../../../client'
import type { useFormMutationErrorHandler } from '../../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../../providers/alerts'
import { detachPromise } from '../../../../utils/detachPromise'
import { useProjectAssignmentSync } from '../useProjectAssignmentSync'

import type { IntegrationFormData } from './integrationFormSchema'

type UseCreateIntegrationOptions = {
  handleError: ReturnType<typeof useFormMutationErrorHandler>
  onBeforeNavigate?: () => void
}

type InitialToolSelection = {
  name: string
  description?: string | null
  enabled: boolean
  parameters?: Record<string, unknown>[] | null
}

type InitialModelSelection = IntegrationsAPI.components['schemas']['InitialModelSelection']

export function useCreateIntegration({ handleError, onBeforeNavigate }: UseCreateIntegrationOptions) {
  const { mutateAsync: createIntegration } = integrationsClient.useMutation('post', '/integrations')
  const { syncAssignments } = useProjectAssignmentSync()
  const queryClient = useQueryClient()
  const { showAlert } = useAlerts()

  return useCallback(
    (
      formData: IntegrationFormData,
      discoveredTools?: InitialToolSelection[],
      discoveredModels?: InitialModelSelection[]
    ) => {
      const context = formData.name ? `Integration "${formData.name}"` : undefined
      const navigateToList = () => {
        detachPromise(tanstackRouter.navigate({ to: AppRoute.Configuration.Integrations.Root }))
      }

      detachPromise(
        (async () => {
          try {
            const created = await createIntegration({
              body: {
                name: formData.name,
                description: formData.description ?? undefined,
                integration_type: formData.integration_type,
                configuration: formData.configuration,
                management_credential_id: formData.management_credential_id ?? undefined,
                scope: formData.scope,
                discovered_tools:
                  formData.integration_type === IntegrationTypeEnum.MCP_SERVER ? (discoveredTools ?? null) : null,
                discovered_models: discoveredModels ?? null,
              },
            })

            if (formData.scope === 'project' && formData.project_ids.length > 0 && created.id) {
              const result = await syncAssignments(created.id, [], formData.project_ids)
              await queryClient.invalidateQueries({ queryKey: ['get', '/integrations/{integration_id}'] })
              await queryClient.invalidateQueries({ queryKey: ['get', '/integrations/{integration_id}/projects'] })
              if (result.errors.length > 0) {
                showAlert({
                  title: 'Integration created with warnings',
                  description: `"${formData.name}" was created but some project assignments failed.`,
                  variant: 'warning',
                  autoDismiss: true,
                })
                onBeforeNavigate?.()
                navigateToList()
                return
              }
            }

            showAlert({
              title: 'Integration created',
              description: `"${formData.name}" has been saved.`,
              variant: 'success',
              autoDismiss: true,
            })
            onBeforeNavigate?.()
            navigateToList()
          } catch (error: unknown) {
            handleError({ title: 'Failed to add integration', context })(error)
          }
        })()
      )
    },
    [createIntegration, syncAssignments, queryClient, handleError, showAlert, onBeforeNavigate]
  )
}
