import type { IntegrationsAPI } from '@syntara/contracts'

import { useDialogState } from '../../../hooks/useDialogState'

import type { Credential, CredentialWorkflowRef } from './credentialConstants'
import { useCredentialIntegrationCheck } from './useCredentialIntegrationCheck'
import { useCredentialWorkflowCheck } from './useCredentialWorkflowCheck'

type Integration = IntegrationsAPI.components['schemas']['IntegrationRead']

type DisableCredentialState = {
  credentialToDisable: Credential | null
  affectedWorkflows: CredentialWorkflowRef[]
  workflowsFetchError: boolean
  isLoadingWorkflows: boolean
  affectedIntegrations: Integration[]
  integrationsFetchError: boolean
  isLoadingIntegrations: boolean
  openDisableDialog: (credential: Credential) => void
  closeDisableDialog: () => void
}

/**
 * Manages state for the disable credential dialog, including affected workflows and integrations.
 *
 * @returns Dialog state, affected resources, loading/error states, and open/close callbacks.
 */
export function useDisableCredentialState(): DisableCredentialState {
  const dialog = useDialogState<Credential>()
  const { affectedWorkflows, workflowsFetchError, isLoadingWorkflows } = useCredentialWorkflowCheck(dialog.item)
  const { affectedIntegrations, integrationsFetchError, isLoadingIntegrations } = useCredentialIntegrationCheck(
    dialog.item?.id ?? null
  )

  return {
    credentialToDisable: dialog.item,
    affectedWorkflows,
    workflowsFetchError,
    isLoadingWorkflows,
    affectedIntegrations,
    integrationsFetchError,
    isLoadingIntegrations,
    openDisableDialog: dialog.open,
    closeDisableDialog: dialog.close,
  }
}
