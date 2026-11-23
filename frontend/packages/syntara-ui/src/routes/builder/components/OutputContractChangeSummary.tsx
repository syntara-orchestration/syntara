import { Content, ExpandableSection, List, ListItem, Stack, StackItem } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'

import { SynLabel } from '../../../components/labels/SynLabel'

type ContractChange = WorkflowAPI.components['schemas']['TriggerBreakingChanges']
type ParentReference = WorkflowAPI.components['schemas']['WorkflowReferenceRead']

type Props = Readonly<{
  context: 'save' | 'publish'
  contractChanges: ContractChange[]
  parentWorkflows: ParentReference[]
}>

type OutputChangeDetail = Readonly<{ key: string; text: string }>

function getOutputChangeDetails(contractChanges: ContractChange[]): OutputChangeDetail[] {
  return contractChanges.flatMap((trigger) =>
    trigger.changes.map((change) => {
      const triggerName = trigger.trigger_name || trigger.trigger_id
      const description =
        change.description.trim().replace(/[.\s]+$/, '') || `${change.change_type}: ${change.field_path}`
      return {
        key: `${trigger.trigger_id}:${change.change_type}:${change.field_path}:${description}`,
        text: `${triggerName}: ${description}`,
      }
    })
  )
}

function summarizeOutputChanges(details: OutputChangeDetail[]): string {
  if (details.length === 0) return 'No declared output changes were detected.'

  const summary = details
    .slice(0, 2)
    .map((detail) => detail.text)
    .join('; ')
  const additionalChangeCount = details.length - 2
  if (additionalChangeCount > 0) {
    const changeLabel = additionalChangeCount === 1 ? 'change' : 'changes'
    return `${summary}; and ${additionalChangeCount} more ${changeLabel}.`
  }
  return `${summary}.`
}

function ParentWorkflowImpact({ parentWorkflows }: Readonly<{ parentWorkflows: ParentReference[] }>) {
  const parentWorkflowCount = new Set(parentWorkflows.map((parent) => parent.workflow_id)).size

  if (parentWorkflowCount === 0) {
    return (
      <StackItem>
        <Content component="p">
          No visible published parent workflows are listed. References outside your visibility scope may not be shown.
        </Content>
      </StackItem>
    )
  }

  return (
    <StackItem>
      <SynLabel color="blue">
        {parentWorkflowCount} visible published parent {parentWorkflowCount === 1 ? 'workflow' : 'workflows'}
      </SynLabel>
      <Content component="p">
        The count includes only parent workflows visible to you. References outside your visibility scope may not be
        shown.
      </Content>
    </StackItem>
  )
}

export function OutputContractChangeSummary({ context, contractChanges, parentWorkflows }: Props) {
  const changeDetails = getOutputChangeDetails(contractChanges)
  const changeSummary = summarizeOutputChanges(changeDetails)
  const impactSummary =
    context === 'publish'
      ? 'Published parent workflows will use the updated child version on their next run.'
      : 'Saving updates this draft only; published parent workflows continue using the latest published child version.'

  return (
    <Stack hasGutter>
      <StackItem>
        <Content component="p">
          Output changes: {changeSummary} {impactSummary}
        </Content>
      </StackItem>
      {changeDetails.length > 0 && (
        <StackItem>
          <ExpandableSection toggleText={`View all ${changeDetails.length} output changes`} isIndented>
            <List isPlain>
              {changeDetails.map((detail) => (
                <ListItem key={detail.key}>{detail.text}</ListItem>
              ))}
            </List>
          </ExpandableSection>
        </StackItem>
      )}
      {context === 'publish' && <ParentWorkflowImpact parentWorkflows={parentWorkflows} />}
    </Stack>
  )
}
