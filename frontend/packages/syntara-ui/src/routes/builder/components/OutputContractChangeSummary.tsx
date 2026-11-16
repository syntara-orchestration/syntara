import {
  Button,
  Content,
  ExpandableSection,
  List,
  ListItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'
import { useState } from 'react'

type ContractChange = WorkflowAPI.components['schemas']['TriggerBreakingChanges']
type ParentReference = WorkflowAPI.components['schemas']['WorkflowReferenceRead']

type Props = Readonly<{
  context: 'save' | 'publish'
  contractChanges: ContractChange[]
  parentWorkflows: ParentReference[]
}>

type ParentWorkflowGroup = {
  workflowId: string
  workflowName: string
  workflowVersion: number
  stepDescriptions: string[]
}

const CHANGE_TYPE_LABELS: Record<string, string> = {
  removed_output: 'Outputs removed',
  type_change: 'Output types changed',
  new_required_output: 'Required outputs added',
  added_output: 'Optional outputs added',
  optional_output: 'Outputs made optional',
  constraint_change: 'Output constraints changed',
}

function getParentWorkflowGroups(references: ParentReference[]): ParentWorkflowGroup[] {
  const groups = new Map<string, ParentWorkflowGroup>()
  for (const reference of references) {
    const stepDescription = reference.step_name || reference.step_id
    const existing = groups.get(reference.workflow_id)
    if (existing) {
      if (!existing.stepDescriptions.includes(stepDescription)) existing.stepDescriptions.push(stepDescription)
      continue
    }
    groups.set(reference.workflow_id, {
      workflowId: reference.workflow_id,
      workflowName: reference.workflow_name,
      workflowVersion: reference.workflow_version,
      stepDescriptions: [stepDescription],
    })
  }
  return [...groups.values()]
}

function groupContractChanges(changes: ContractChange[]) {
  const counts = new Map<string, number>()
  for (const trigger of changes) {
    for (const change of trigger.changes) {
      const label = CHANGE_TYPE_LABELS[change.change_type] ?? 'Other output changes'
      counts.set(label, (counts.get(label) ?? 0) + 1)
    }
  }
  return [...counts.entries()]
}

function ParentWorkflowReferencesModal({
  isOpen,
  onClose,
  parentWorkflows,
}: Readonly<{
  isOpen: boolean
  onClose: () => void
  parentWorkflows: ParentReference[]
}>) {
  const parentGroups = getParentWorkflowGroups(parentWorkflows)

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="medium" aria-label="Visible published parent workflows">
      <ModalHeader title="Visible published parent workflows" />
      <ModalBody>
        <Content component="p">
          These {parentGroups.length} visible parent workflows will use the updated child version on their next run.
          References outside your visibility scope may not be listed.
        </Content>
        <List isPlain>
          {parentGroups.map((parent) => (
            <ListItem key={parent.workflowId}>
              {parent.workflowName} (parent v{parent.workflowVersion}) — {parent.stepDescriptions.join(', ')}
            </ListItem>
          ))}
        </List>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </ModalFooter>
    </Modal>
  )
}

function ParentWorkflowImpact({
  context,
  parentWorkflows,
}: Readonly<{
  context: 'save' | 'publish'
  parentWorkflows: ParentReference[]
}>) {
  const [isParentReferencesOpen, setIsParentReferencesOpen] = useState(false)
  const parentWorkflowCount = getParentWorkflowGroups(parentWorkflows).length

  if (context === 'save') {
    return (
      <StackItem>
        <Content component="p">
          Saving updates this draft only. Zero published parent workflows are affected; they continue using the latest
          published child version.
        </Content>
      </StackItem>
    )
  }

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
    <>
      <StackItem>
        <Content component="h4">{parentWorkflowCount} visible published parent workflows affected</Content>
        <Content component="p">
          They will use the updated child version on their next run. References outside your visibility scope may not be
          listed.
        </Content>
        <Button variant="link" onClick={() => setIsParentReferencesOpen(true)}>
          View visible parent workflows
        </Button>
      </StackItem>
      <ParentWorkflowReferencesModal
        isOpen={isParentReferencesOpen}
        onClose={() => setIsParentReferencesOpen(false)}
        parentWorkflows={parentWorkflows}
      />
    </>
  )
}

export function OutputContractChangeSummary({ context, contractChanges, parentWorkflows }: Props) {
  const changeCounts = groupContractChanges(contractChanges)
  const totalChangeCount = changeCounts.reduce((total, [, count]) => total + count, 0)

  return (
    <Stack hasGutter>
      <StackItem>
        <Content component="p">These changes affect the values and fields exposed by the child workflow.</Content>
      </StackItem>
      {totalChangeCount > 0 ? (
        <StackItem>
          <Content component="h4">Output contract changes</Content>
          <List isPlain>
            {changeCounts.map(([label, count]) => (
              <ListItem key={label}>
                {label}: {count}
              </ListItem>
            ))}
          </List>
          <ExpandableSection toggleText={`View details for ${totalChangeCount} output changes`} isIndented>
            {contractChanges.map((trigger) => (
              <Stack hasGutter key={trigger.trigger_id}>
                <StackItem>
                  <Content component="h4">{trigger.trigger_name || trigger.trigger_id}</Content>
                  <List isPlain>
                    {trigger.changes.map((change) => (
                      <ListItem key={`${change.change_type}-${change.field_path}`}>{change.description}</ListItem>
                    ))}
                  </List>
                </StackItem>
              </Stack>
            ))}
          </ExpandableSection>
        </StackItem>
      ) : (
        <StackItem>
          <Content component="p">No output field changes are included in this review.</Content>
        </StackItem>
      )}
      <ParentWorkflowImpact context={context} parentWorkflows={parentWorkflows} />
    </Stack>
  )
}
