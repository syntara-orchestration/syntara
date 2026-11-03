import { RhUiArrowRightIcon } from '@patternfly/react-icons'

import { SynLink } from '../../../components/SynLink'

/**
 * Contextual "View sub-workflow run" link to a child execution. Shared by the
 * Overview table, the Details activity list, and the selected-node header so the
 * navigation is defined once. Rendered via SynLink (a PatternFly inline link
 * button backed by TanStack Router) so it keeps anchor semantics: open in a new
 * tab, copy link, and client-side routing.
 */
export function SubWorkflowRunLink({
  childExecutionId,
  childName,
}: Readonly<{ childExecutionId: string; childName: string | null }>) {
  return (
    <SynLink to={`/executions/${childExecutionId}`} onClick={(event) => event.stopPropagation()}>
      View sub-workflow run{childName ? `: ${childName}` : ''} <RhUiArrowRightIcon />
    </SynLink>
  )
}
