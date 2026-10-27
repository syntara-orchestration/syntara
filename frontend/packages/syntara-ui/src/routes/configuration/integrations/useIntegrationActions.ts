import { IntegrationTypeEnum } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../../app/AppRoute'
import { integrationsClient } from '../../../client'
import { useDialogState } from '../../../hooks/useDialogState'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'

import type { IntegrationRead } from './integrationTypes'

export function useIntegrationActions(refetch: () => Promise<unknown>) {
  const navigate = useNavigate()
  const { showAlert } = useAlerts()

  const validateDialog = useDialogState<IntegrationRead>()
  const deleteDialog = useDialogState<IntegrationRead>()
  const disableDialog = useDialogState<IntegrationRead>()

  const { mutate: validateIntegration } = integrationsClient.useMutation(
    'post',
    '/integrations/{integration_id}/validate'
  )
  const { mutate: deleteIntegration } = integrationsClient.useMutation('delete', '/integrations/{integration_id}')
  const { mutate: patchKafkaIntegration } = integrationsClient.useMutation(
    'patch',
    '/kafka-integrations/{integration_id}'
  )
  const { mutate: patchIntegration } = integrationsClient.useMutation('patch', '/integrations/{integration_id}')

  function handleValidate() {
    const item = validateDialog.item
    if (!item?.id) return

    validateIntegration(
      { params: { path: { integration_id: item.id } } },
      {
        onSuccess: (result) => {
          showAlert({
            title: result.success ? 'Validation successful' : 'Validation failed',
            description: result.success
              ? `"${item.name}" validated successfully.`
              : (result.error ?? `"${item.name}" could not be validated.`),
            variant: result.success ? 'success' : 'danger',
            autoDismiss: true,
          })
          detachPromise(refetch())
        },
        onError: (error: unknown) => {
          showAlert({
            title: 'Validation failed',
            description: `Failed to validate "${item.name}": ${getErrorMessage(error)}`,
            variant: 'danger',
            autoDismiss: true,
          })
          detachPromise(refetch())
        },
        onSettled: () => validateDialog.close(),
      }
    )
  }

  function handleDelete() {
    const item = deleteDialog.item
    if (!item?.id) return

    deleteIntegration(
      { params: { path: { integration_id: item.id } } },
      {
        onSuccess: () => {
          showAlert({
            title: 'Integration deleted',
            description: `"${item.name}" has been deleted.`,
            variant: 'success',
            autoDismiss: true,
          })
          detachPromise(refetch())
          detachPromise(navigate({ to: AppRoute.Configuration.Integrations.Root }))
        },
        onError: (error: unknown) => {
          showAlert({
            title: 'Delete failed',
            description: `Failed to delete "${item.name}": ${getErrorMessage(error)}`,
            variant: 'danger',
            autoDismiss: true,
          })
        },
        onSettled: () => deleteDialog.close(),
      }
    )
  }

  function handleToggleEnabled(integration: IntegrationRead) {
    if (!integration.id) return

    if (integration.enabled) {
      disableDialog.open(integration)
      return
    }

    const patch = integration.integration_type === IntegrationTypeEnum.KAFKA ? patchKafkaIntegration : patchIntegration
    patch(
      {
        params: { path: { integration_id: integration.id } },
        body: { enabled: true },
      },
      {
        onSuccess: () => detachPromise(refetch()),
        onError: (error: unknown) => {
          showAlert({
            title: 'Update failed',
            description: `Failed to enable "${integration.name}": ${getErrorMessage(error)}`,
            variant: 'danger',
            autoDismiss: true,
          })
        },
      }
    )
  }

  function handleDisable() {
    const item = disableDialog.item
    if (!item?.id) return

    const patch = item.integration_type === IntegrationTypeEnum.KAFKA ? patchKafkaIntegration : patchIntegration
    patch(
      {
        params: { path: { integration_id: item.id } },
        body: { enabled: false },
      },
      {
        onSuccess: () => detachPromise(refetch()),
        onError: (error: unknown) => {
          showAlert({
            title: 'Update failed',
            description: `Failed to disable "${item.name}": ${getErrorMessage(error)}`,
            variant: 'danger',
            autoDismiss: true,
          })
        },
        onSettled: () => disableDialog.close(),
      }
    )
  }

  return {
    validateDialog,
    deleteDialog,
    disableDialog,
    handleValidate,
    handleDelete,
    handleToggleEnabled,
    handleDisable,
  }
}
