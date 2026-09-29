import { Stack, StackItem } from '@patternfly/react-core'

import {
  WORKFLOW_STATE_DRAFT_HELP,
  WORKFLOW_STATE_PUBLISHED_HELP,
  WORKFLOW_STATE_UNPUBLISHED_CHANGES_HELP,
} from './workflowStateColumnHelpText'

export function WorkflowStateColumnHelpBody() {
  return (
    <Stack hasGutter>
      <StackItem>
        <strong>Draft</strong>: {WORKFLOW_STATE_DRAFT_HELP}
      </StackItem>
      <StackItem>
        <strong>Published</strong>: {WORKFLOW_STATE_PUBLISHED_HELP}
      </StackItem>
      <StackItem>
        <strong>Unpublished changes</strong>: {WORKFLOW_STATE_UNPUBLISHED_CHANGES_HELP}
      </StackItem>
    </Stack>
  )
}
