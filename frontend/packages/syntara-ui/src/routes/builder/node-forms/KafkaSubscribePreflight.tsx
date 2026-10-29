import { Alert, Button, Content, ContentVariants, Stack, StackItem } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'

import { workflowClient } from '../../../client'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useBuilderPermissions } from '../useBuilderPermissions'

import type { KafkaSubscribeParameters } from './kafkaSubscribeMapping'

type PreflightResult = WorkflowAPI.components['schemas']['EventSubscriptionTestResponse']
type KafkaSubscribePreflightProps = Readonly<{
  workflowId?: string | null
  projectId?: string
  parameters?: KafkaSubscribeParameters
  isReadOnly: boolean
}>

/** Keyed by configuration by its parent so pending or old results cannot describe new fields. */
export function KafkaSubscribePreflight({
  workflowId,
  projectId,
  parameters,
  isReadOnly,
}: KafkaSubscribePreflightProps) {
  const permissions = useBuilderPermissions(!workflowId, false, projectId)
  const handleError = useMutationErrorHandler()
  const mutation = workflowClient.useMutation('post', '/workflows/{workflow_id}/event_subscriptions/test')
  const canTest = Boolean(workflowId && parameters && permissions.canEdit && !isReadOnly && !mutation.isPending)
  const testAccess = () => {
    if (!canTest || !workflowId || !parameters) return
    mutation.mutate(
      { params: { path: { workflow_id: workflowId } }, body: parameters },
      {
        onError: handleError({ title: 'Unable to test Kafka runtime access' }),
      }
    )
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <DisabledWithTooltip isDisabled={!permissions.canEdit} content={permissions.tooltips.edit}>
          <Button variant="secondary" isAriaDisabled={!canTest} isLoading={mutation.isPending} onClick={testAccess}>
            Test runtime access
          </Button>
        </DisabledWithTooltip>
      </StackItem>
      {!workflowId && (
        <StackItem>
          <Content component={ContentVariants.p}>Save the workflow before testing runtime access.</Content>
        </StackItem>
      )}
      {workflowId && !parameters && (
        <StackItem>
          <Content component={ContentVariants.p}>
            Select an Integration, runtime credential, and valid topic and schema before testing.
          </Content>
        </StackItem>
      )}
      <StackItem>
        <Content component={ContentVariants.p}>
          This check does not consume messages or preview payloads. Integration health and runtime access are separate
          checks.
        </Content>
      </StackItem>
      <StackItem aria-live="polite" aria-atomic>
        {mutation.isPending && <Content component={ContentVariants.p}>Checking runtime access…</Content>}
        {mutation.isError && (
          <SynErrorState title="Unable to test Kafka runtime access" message={mutation.error} onRetry={testAccess} />
        )}
        {mutation.data && <KafkaPreflightResult result={mutation.data} />}
      </StackItem>
    </Stack>
  )
}

function KafkaPreflightResult({ result }: Readonly<{ result: PreflightResult }>) {
  return (
    <Alert
      variant={result.success ? 'info' : 'warning'}
      isInline
      title={result.success ? 'Connection and topic metadata checked' : 'Runtime access check failed'}
      component="h4"
    >
      <Content>
        <Content component={ContentVariants.p}>
          Connection: {result.connection ?? 'unverified'}. Topic metadata: {result.topic_metadata ?? 'unverified'}.
        </Content>
        <Content component={ContentVariants.p}>
          Topic read permission: unverified. Consumer group access: unverified. A successful check does not prove
          permission to consume messages.
        </Content>
      </Content>
    </Alert>
  )
}
