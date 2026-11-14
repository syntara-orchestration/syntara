import { Content, List, ListItem, Stack, StackItem } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'

type Props = Readonly<{
  contractChanges: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  parentWorkflows: WorkflowAPI.components['schemas']['WorkflowReferenceRead'][]
}>

function getParentReferenceDescription(reference: WorkflowAPI.components['schemas']['WorkflowReferenceRead']): string {
  const stepName = reference.step_name || reference.step_id
  return `${reference.workflow_name} (parent v${reference.workflow_version}) — ${stepName}`
}

export function OutputContractChangeSummary({ contractChanges, parentWorkflows }: Props) {
  return (
    <Stack hasGutter>
      <StackItem>
        <Content component="p">These changes affect the values and fields exposed by the child workflow.</Content>
      </StackItem>
      {contractChanges.map((trigger) => (
        <StackItem key={trigger.trigger_id}>
          <Content component="h4">{trigger.trigger_name || trigger.trigger_id}</Content>
          <List isPlain>
            {trigger.changes.map((change) => (
              <ListItem key={`${change.change_type}-${change.field_path}`}>{change.description}</ListItem>
            ))}
          </List>
        </StackItem>
      ))}
      {parentWorkflows.length > 0 ? (
        <StackItem>
          <Content component="h4">Published parent workflow references</Content>
          <List isPlain>
            {parentWorkflows.map((reference) => (
              <ListItem key={`${reference.workflow_id}-${reference.step_id}`}>
                {getParentReferenceDescription(reference)}
              </ListItem>
            ))}
          </List>
          <Content component="p">
            If you publish these changes, each listed parent workflow will use the updated child version on its next
            run.
          </Content>
        </StackItem>
      ) : (
        <StackItem>
          <Content component="p">No published parent workflows currently reference this child.</Content>
        </StackItem>
      )}
    </Stack>
  )
}
