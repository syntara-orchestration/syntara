import { Content, ExpandableSection, List, ListItem, Stack, StackItem } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'

import { SynLabel } from '../../../components/labels/SynLabel'

type ContractChange = WorkflowAPI.components['schemas']['TriggerBreakingChanges']
type ParentReference = WorkflowAPI.components['schemas']['WorkflowReferenceRead']

type Props = Readonly<{
  context: 'save' | 'publish'
  contractChanges: ContractChange[]
  breakingChanges?: ContractChange[]
  hasBreakingChanges?: boolean
  parentWorkflows: ParentReference[]
}>

type OutputChangeDetail = Readonly<{
  key: string
  text: string
  changeType: string
  fieldPath: string
  oldType?: string | null
  newType?: string | null
  triggerName: string
}>

function getOutputChangeDetails(contractChanges: ContractChange[]): OutputChangeDetail[] {
  const schemaChangeKeys = new Set(
    contractChanges.flatMap((trigger) =>
      trigger.changes
        .filter((change) => change.change_type !== 'mapping_changed')
        .map((change) => `${trigger.trigger_id}:${change.field_path}`)
    )
  )

  return contractChanges.flatMap((trigger) => {
    return trigger.changes.flatMap((change) => {
      const changeKey = `${trigger.trigger_id}:${change.field_path}`
      if (change.change_type === 'mapping_changed' && schemaChangeKeys.has(changeKey)) return []

      const triggerName = trigger.trigger_name || trigger.trigger_id
      const rawDescription =
        change.description.trim().replace(/[.\s]+$/, '') || `${change.change_type}: ${change.field_path}`
      const typeDetails =
        change.old_type && change.new_type && change.old_type !== change.new_type
          ? `${change.old_type} → ${change.new_type}`
          : change.old_type || change.new_type
      const description =
        typeDetails && !rawDescription.includes(typeDetails) ? `${rawDescription} (${typeDetails})` : rawDescription
      return {
        key: `${trigger.trigger_id}:${change.change_type}:${change.field_path}:${description}`,
        text: `${triggerName}: ${description}`,
        changeType: change.change_type,
        fieldPath: change.field_path,
        oldType: change.old_type,
        newType: change.new_type,
        triggerName,
      }
    })
  })
}

function describeOutputChange(change: OutputChangeDetail): string {
  const outputName = `“${change.fieldPath}”`
  switch (change.changeType) {
    case 'removed_output':
      return `removes the output ${outputName}`
    case 'type_change':
      return `changes the type of the output ${outputName}`
    case 'new_required_output':
      return `adds the required output ${outputName}`
    case 'required_output':
      return `makes the output ${outputName} required`
    case 'added_output':
      return `adds the optional output ${outputName}`
    case 'optional_output':
      return `makes the output ${outputName} optional`
    case 'constraint_change':
      if (change.fieldPath === '$root') return 'changes root-level validation constraints'
      return `changes validation constraints for the output ${outputName}`
    case 'removed_trigger':
      return `removes the Subworkflow Trigger “${change.triggerName}”`
    case 'mapping_changed':
      return `changes the source mapping for the output ${outputName}`
    default:
      return `changes the output ${outputName}`
  }
}

function summarizeOutputChanges(details: OutputChangeDetail[], context: Props['context']): string {
  if (details.length === 0) return 'No declared output changes were detected.'

  const versionKind = context === 'publish' ? 'This version' : 'This draft'
  const firstChange = describeOutputChange(details[0])
  const additionalChangeCount = details.length - 1
  if (additionalChangeCount === 0) return `${versionKind} ${firstChange}.`

  const changeLabel =
    additionalChangeCount === 1 ? 'additional output contract change' : 'additional output contract changes'
  return `${versionKind} ${firstChange} and ${additionalChangeCount} ${changeLabel}.`
}

function shouldShowDetails(details: OutputChangeDetail[]): boolean {
  if (details.length > 1) return true
  return details.some((detail) => detail.changeType !== 'removed_output' && Boolean(detail.oldType || detail.newType))
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
      <SynLabel color="grey">
        Used by {parentWorkflowCount} visible published {parentWorkflowCount === 1 ? 'workflow' : 'workflows'}
      </SynLabel>
    </StackItem>
  )
}

export function OutputContractChangeSummary({
  context,
  contractChanges,
  breakingChanges,
  hasBreakingChanges = false,
  parentWorkflows,
}: Props) {
  const changesToSummarize =
    context === 'publish' && hasBreakingChanges ? (breakingChanges ?? contractChanges) : contractChanges
  const changeDetails = getOutputChangeDetails(changesToSummarize)
  const changeSummary = summarizeOutputChanges(changeDetails, context)
  const impactSummary =
    context === 'publish'
      ? 'Published parent workflows will use the updated child version on their next run.'
      : 'Saving updates this draft only; published parent workflows continue using the latest published child version.'

  return (
    <Stack hasGutter>
      <StackItem>
        <Content component="p">
          {changeSummary} {impactSummary}
        </Content>
      </StackItem>
      {shouldShowDetails(changeDetails) && (
        <StackItem>
          <ExpandableSection toggleText="View output change details" isIndented>
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
