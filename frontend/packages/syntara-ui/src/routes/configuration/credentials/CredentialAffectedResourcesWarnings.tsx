import { Alert, Content, ContentVariants, Stack, StackItem } from '@patternfly/react-core'
import type { IntegrationsAPI } from '@syntara/contracts'

import type { CredentialWorkflowRef } from './credentialConstants'
import { CredentialDependencySection } from './CredentialDependencySection'

type Integration = IntegrationsAPI.components['schemas']['IntegrationRead']

type CredentialAffectedResourcesWarningsProps = {
  affectedWorkflows: CredentialWorkflowRef[]
  workflowsFetchError: boolean
  affectedIntegrations: Integration[]
  integrationsFetchError: boolean
  /**
   * When true, integrations are rendered as a hard blocker (separate danger alert,
   * "must be detached" copy) instead of being grouped under the generic "Resources
   * that will be affected" summary. Used by the delete dialog, where the backend
   * rejects the delete outright while any integration still references the
   * credential — unlike workflows, which are only warned about, not blocking.
   */
  integrationsBlockDeletion?: boolean
}

/**
 * Shared ripple-effect dependency summary for credential delete/disable dialogs:
 * fetch-error alerts, then a single "Resources that will be affected" header with
 * badge rows per resource type.
 */
export function CredentialAffectedResourcesWarnings({
  affectedWorkflows,
  workflowsFetchError,
  affectedIntegrations,
  integrationsFetchError,
  integrationsBlockDeletion = false,
}: Readonly<CredentialAffectedResourcesWarningsProps>) {
  const hasWorkflows = affectedWorkflows.length > 0
  const hasIntegrations = affectedIntegrations.length > 0
  const hasBlockingIntegrations = integrationsBlockDeletion && hasIntegrations
  const hasDependencies = hasWorkflows || (hasIntegrations && !hasBlockingIntegrations)
  const hasFetchError = workflowsFetchError || integrationsFetchError

  if (!hasDependencies && !hasBlockingIntegrations && !hasFetchError) return null

  return (
    <Stack hasGutter>
      {workflowsFetchError && (
        <StackItem>
          <Alert variant="warning" isInline isPlain title="Unable to check which workflows use this credential.">
            Proceeding may affect workflows that reference this credential.
          </Alert>
        </StackItem>
      )}
      {integrationsFetchError && (
        <StackItem>
          <Alert variant="warning" isInline isPlain title="Unable to check which integrations use this credential.">
            Proceeding may affect integrations that reference this credential.
          </Alert>
        </StackItem>
      )}
      {hasBlockingIntegrations && (
        <StackItem>
          <Alert
            variant="danger"
            isInline
            title="This credential can't be deleted until it's detached from these integrations"
          >
            <CredentialDependencySection label="Integrations" resources={affectedIntegrations} />
          </Alert>
        </StackItem>
      )}
      {hasDependencies && (
        <StackItem>
          <Stack hasGutter>
            <StackItem>
              <Content component={ContentVariants.p}>
                <strong>Resources that will be affected</strong>
              </Content>
            </StackItem>
            {hasWorkflows && (
              <StackItem>
                <CredentialDependencySection label="Workflows" resources={affectedWorkflows} />
              </StackItem>
            )}
            {hasIntegrations && !hasBlockingIntegrations && (
              <StackItem>
                <CredentialDependencySection label="Integrations" resources={affectedIntegrations} />
              </StackItem>
            )}
          </Stack>
        </StackItem>
      )}
    </Stack>
  )
}
