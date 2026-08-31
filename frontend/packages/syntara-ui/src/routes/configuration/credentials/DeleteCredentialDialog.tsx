import { Content, ContentVariants, Spinner, Stack, StackItem } from '@patternfly/react-core'
import type { IntegrationsAPI } from '@syntara/contracts'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'

import { CredentialAffectedResourcesWarnings } from './CredentialAffectedResourcesWarnings'
import type { Credential, CredentialWorkflowRef } from './credentialConstants'

type Integration = IntegrationsAPI.components['schemas']['IntegrationRead']

type DeleteCredentialDialogProps = {
  credential: Credential | null
  affectedWorkflows: CredentialWorkflowRef[]
  workflowsFetchError: boolean
  isLoadingWorkflows: boolean
  affectedIntegrations: Integration[]
  integrationsFetchError: boolean
  isLoadingIntegrations: boolean
  isLoading?: boolean
  onConfirm: () => void
  onClose: () => void
}

export function DeleteCredentialDialog({
  credential,
  affectedWorkflows,
  workflowsFetchError,
  isLoadingWorkflows,
  affectedIntegrations,
  integrationsFetchError,
  isLoadingIntegrations,
  isLoading,
  onConfirm,
  onClose,
}: Readonly<DeleteCredentialDialogProps>) {
  if (!credential) return null

  const isLoadingChecks = isLoadingWorkflows || isLoadingIntegrations
  // Integrations are a hard block: the backend rejects the delete outright while any
  // integration still references the credential (unlike workflows, which are only
  // warned about). Don't invite a confirmation the backend can never honor.
  const hasBlockingIntegrations = affectedIntegrations.length > 0
  const hasWorkflowDependency = affectedWorkflows.length > 0
  const showAffectedResources =
    hasWorkflowDependency || hasBlockingIntegrations || workflowsFetchError || integrationsFetchError

  return (
    <SynConfirmationDialog
      isOpen
      onClose={onClose}
      onConfirm={onConfirm}
      title="Delete credential?"
      confirmLabel={hasBlockingIntegrations ? 'Detach integrations first' : 'Delete'}
      confirmVariant="danger"
      titleIconVariant="warning"
      confirmLoading={isLoading || isLoadingChecks}
      confirmDisabled={hasBlockingIntegrations}
      destructiveAcknowledgement={
        hasBlockingIntegrations
          ? undefined
          : {
              checkboxId: 'delete-credential-ack',
              label: hasWorkflowDependency
                ? 'I understand this credential and the resources shown above will be affected by this deletion.'
                : 'I understand this credential will be permanently deleted.',
            }
      }
    >
      {isLoadingChecks ? (
        <Content component={ContentVariants.p}>
          <Spinner size="md" aria-label="Checking usage" /> Checking for workflows and integrations that use this
          credential…
        </Content>
      ) : (
        <Stack hasGutter>
          <StackItem>
            {hasBlockingIntegrations ? (
              <Content component={ContentVariants.p}>
                The credential <strong>{credential.name}</strong> can&apos;t be deleted while it&apos;s still used by
                the integration(s) below. Detach it from each one, then try again.
              </Content>
            ) : (
              <Content component={ContentVariants.p}>
                The credential <strong>{credential.name}</strong> will be deleted. This cannot be undone.
              </Content>
            )}
          </StackItem>
          {showAffectedResources && (
            <StackItem>
              <CredentialAffectedResourcesWarnings
                affectedWorkflows={affectedWorkflows}
                workflowsFetchError={workflowsFetchError}
                affectedIntegrations={affectedIntegrations}
                integrationsFetchError={integrationsFetchError}
                integrationsBlockDeletion={hasBlockingIntegrations}
              />
            </StackItem>
          )}
        </Stack>
      )}
    </SynConfirmationDialog>
  )
}
