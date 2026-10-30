import { Button } from '@patternfly/react-core'
import { RhUiArrowRightIcon } from '@patternfly/react-icons'
import { useNavigate } from '@tanstack/react-router'

import { detachPromise } from '../../../utils/detachPromise'

/**
 * Contextual "View sub-workflow run" link to a child execution. Shared by the
 * Overview table, the Details activity list, and the selected-node header so the
 * navigation is defined once. Navigates via the typed execution route.
 */
export function SubWorkflowRunLink({
  childExecutionId,
  childName,
}: Readonly<{ childExecutionId: string; childName: string | null }>) {
  const navigate = useNavigate()
  return (
    <Button
      variant="link"
      isInline
      icon={<RhUiArrowRightIcon />}
      iconPosition="end"
      onClick={(event) => {
        event.stopPropagation()
        detachPromise(navigate({ to: '/executions/$executionId', params: { executionId: childExecutionId } }))
      }}
    >
      View sub-workflow run{childName ? `: ${childName}` : ''}
    </Button>
  )
}
