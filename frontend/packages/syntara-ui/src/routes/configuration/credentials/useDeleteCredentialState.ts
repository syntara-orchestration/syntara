import type { IntegrationsAPI } from '@syntara/contracts'

import { useDialogState } from '../../../hooks/useDialogState'

import type { Credential, CredentialWorkflowRef } from './credentialConstants'
import { useCredentialIntegrationCheck } from './useCredentialIntegrationCheck'
import { useCredentialWorkflowCheck } from './useCredentialWorkflowCheck'

type Integration = IntegrationsAPI.components['schemas']['IntegrationRead']

type DeleteCredentialState = {
  credentialToDelete: Credential | null
  affectedWorkflows: CredentialWorkflowRef[]
  workflowsFetchError: boolean
  isLoadingWorkflows: boolean
  affectedIntegrations: Integration[]
  integrationsFetchError: boolean
  isLoadingIntegrations: boolean
  openDeleteDialog: (credential: Credential) => void
  closeDeleteDialog: () => void
}

/**
 * Manages state for the delete credential dialog, including affected workflows and integrations.
 *
 * @returns Dialog state, affected resources, loading/error states, and open/close callbacks.
 */
export function useDeleteCredentialState(): DeleteCredentialState {
  const dialog = useDialogState<Credential>()
  const { affectedWorkflows, workflowsFetchError, isLoadingWorkflows } = useCredentialWorkflowCheck(dialog.item)
  const { affectedIntegrations, integrationsFetchError, isLoadingIntegrations } = useCredentialIntegrationCheck(
    dialog.item?.id ?? null
  )

  return {
    credentialToDelete: dialog.item,
    affectedWorkflows,
    workflowsFetchError,
    isLoadingWorkflows,
    affectedIntegrations,
    integrationsFetchError,
    isLoadingIntegrations,
    openDeleteDialog: dialog.open,
    closeDeleteDialog: dialog.close,
  }
}
