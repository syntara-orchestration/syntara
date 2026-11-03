import type { ThProps } from '@patternfly/react-table'

import { WorkflowStateColumnHelpBody } from './workflowStateColumnHelp'

/** Column header popover for the workflows table State column. */
export const workflowStateColumnInfo: NonNullable<ThProps['info']> = {
  popover: <WorkflowStateColumnHelpBody />,
  popoverProps: {
    headerContent: 'Workflow state',
  },
  ariaLabel: 'Workflow state help',
}
