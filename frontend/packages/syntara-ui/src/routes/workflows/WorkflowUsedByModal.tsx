import {
  Button,
  Content,
  List,
  ListItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Spinner,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { useState, type ReactNode } from 'react'

import { SynLink } from '../../components/SynLink'

import { useWorkflowUsedBy } from './useWorkflowUsedBy'

type WorkflowUsedByModalProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  workflowId: string | undefined
  /** Optional: restrict to parents invoking these child Subworkflow Trigger nodes. */
  triggerNodeIds?: string[]
}>

/** Page size for the drill-down list; keeps the modal compact even with large counts. */
const PAGE_SIZE = 10

/**
 * Drill-down for the Used-By summary: a paginated list of the published workflows that use this
 * workflow as a sub-workflow, with clickable names. ``total_count`` is the unfiltered total;
 * only parents the caller may view are listed, and parents in projects the caller cannot access
 * are not shown (so the page size is not a reliable "hidden" count — we state this plainly
 * instead of computing a misleading difference).
 */
export function WorkflowUsedByModal({ isOpen, onClose, workflowId, triggerNodeIds }: WorkflowUsedByModalProps) {
  const [cursor, setCursor] = useState<string | undefined>(undefined)
  const { totalCount, referencingParents, next, prev, isLoading, isError } = useWorkflowUsedBy(workflowId, {
    enabled: isOpen,
    cursor,
    triggerNodeIds,
    limit: PAGE_SIZE,
  })

  const handleClose = () => {
    setCursor(undefined)
    onClose()
  }

  let listContent: ReactNode
  if (isLoading) {
    listContent = <Spinner size="md" aria-label="Loading workflows" />
  } else if (isError) {
    listContent = <Content component="p">Unable to load the list of workflows right now.</Content>
  } else if (referencingParents.length > 0) {
    listContent = (
      <List isPlain>
        {referencingParents.map((parent) => (
          <ListItem key={parent.id}>
            <SynLink to={`/workflow-builder/${parent.id}`}>{parent.name}</SynLink>
          </ListItem>
        ))}
      </List>
    )
  } else {
    listContent = <Content component="p">No workflows you can access use this workflow.</Content>
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium" aria-label="Workflows that use this workflow">
      <ModalHeader title="Used by published workflows" />
      <ModalBody>
        <Stack hasGutter>
          {!isLoading && !isError && (
            <StackItem>
              <Content component="p">
                {totalCount} published {totalCount === 1 ? 'workflow uses' : 'workflows use'} this workflow as a
                sub-workflow.
              </Content>
            </StackItem>
          )}
          <StackItem>{listContent}</StackItem>
          {!isLoading && !isError && (
            <StackItem>
              <Content component="small">Only workflows you have permission to view are listed.</Content>
            </StackItem>
          )}
        </Stack>
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={() => setCursor(prev ?? undefined)} isDisabled={!prev || isLoading}>
          Previous
        </Button>
        <Button variant="secondary" onClick={() => setCursor(next ?? undefined)} isDisabled={!next || isLoading}>
          Next
        </Button>
        <Button variant="link" onClick={handleClose}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
  )
}
