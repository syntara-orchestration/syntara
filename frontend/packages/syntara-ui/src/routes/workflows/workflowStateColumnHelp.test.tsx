import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { WorkflowStateColumnHelpBody } from './workflowStateColumnHelp'
import {
  WORKFLOW_STATE_DRAFT_HELP,
  WORKFLOW_STATE_PUBLISHED_HELP,
  WORKFLOW_STATE_UNPUBLISHED_CHANGES_HELP,
} from './workflowStateColumnHelpText'
import { workflowStateColumnInfo } from './workflowStateColumnInfo'

describe('WorkflowStateColumnHelpBody', () => {
  it('renders help copy for draft, published, and unpublished changes', () => {
    const { container } = render(<WorkflowStateColumnHelpBody />)

    expect(container).toHaveTextContent(WORKFLOW_STATE_DRAFT_HELP)
    expect(container).toHaveTextContent(WORKFLOW_STATE_PUBLISHED_HELP)
    expect(container).toHaveTextContent(WORKFLOW_STATE_UNPUBLISHED_CHANGES_HELP)
    expect(screen.getByText('Draft', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Published', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Unpublished changes', { selector: 'strong' })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<WorkflowStateColumnHelpBody />)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('workflowStateColumnInfo', () => {
  it('defines popover header and trigger aria label', () => {
    expect(workflowStateColumnInfo.popoverProps?.headerContent).toBe('Workflow state')
    expect(workflowStateColumnInfo.ariaLabel).toBe('Workflow state help')
  })
})
