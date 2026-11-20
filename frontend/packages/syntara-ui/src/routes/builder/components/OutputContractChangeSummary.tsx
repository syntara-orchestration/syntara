import {
  Button,
  Content,
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

import { SynLabel } from '../../../components/labels/SynLabel'

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
  const parentNoun = parentGroups.length === 1 ? 'workflow' : 'workflows'

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="medium" aria-label="Visible published parent workflows">
      <ModalHeader title="Visible published parent workflows" />
      <ModalBody>
        <Content component="p">
          These {parentGroups.length} visible parent {parentNoun} will use the updated child version on their next run.
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
          Saving updates this draft only. Published parent workflows continue using the latest published child version.
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
        <Content component="p">
          Published parent workflows will use the updated child version on their next run.
        </Content>
        <SynLabel color="blue">
          {parentWorkflowCount} visible published parent {parentWorkflowCount === 1 ? 'workflow' : 'workflows'}
        </SynLabel>
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
  return (
    <Stack hasGutter>
      <StackItem>
        <Content component="p">
          {contractChanges.length > 0
            ? 'The child workflow’s declared output contract is changing.'
            : 'No declared output contract changes are included in this review.'}
        </Content>
      </StackItem>
      <ParentWorkflowImpact context={context} parentWorkflows={parentWorkflows} />
    </Stack>
  )
}
