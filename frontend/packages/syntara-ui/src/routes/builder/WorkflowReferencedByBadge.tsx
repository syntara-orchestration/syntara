import { Button } from '@patternfly/react-core'
import { useState } from 'react'

import { SynLabel } from '../../components/labels/SynLabel'
import { useWorkflowUsedBy } from '../workflows/useWorkflowUsedBy'
import { WorkflowUsedByModal } from '../workflows/WorkflowUsedByModal'

type WorkflowReferencedByBadgeProps = Readonly<{
  workflowId: string | undefined
}>

/**
 * "Used by N" badge shown when a workflow is used as a sub-workflow by one or more published
 * parents. The count is the unfiltered total; clicking opens the Used-By drill-down, which lists
 * only the parents the caller may view. A failed lookup renders a distinct "unavailable" state so
 * it is not mistaken for a confirmed zero.
 */
export function WorkflowReferencedByBadge({ workflowId }: WorkflowReferencedByBadgeProps) {
  const { totalCount, isError } = useWorkflowUsedBy(workflowId)
  const [isModalOpen, setIsModalOpen] = useState(false)

  if (!workflowId) return null

  if (isError) {
    return (
      <SynLabel color="grey" aria-label="Used-by count unavailable">
        Used by: unavailable
      </SynLabel>
    )
  }

  if (totalCount === 0) return null

  return (
    <>
      <Button
        variant="plain"
        onClick={() => setIsModalOpen(true)}
        aria-label={`Used by ${totalCount} published workflows. View list.`}
      >
        <SynLabel color="grey">Used by {totalCount}</SynLabel>
      </Button>
      {isModalOpen && <WorkflowUsedByModal isOpen onClose={() => setIsModalOpen(false)} workflowId={workflowId} />}
    </>
  )
}
