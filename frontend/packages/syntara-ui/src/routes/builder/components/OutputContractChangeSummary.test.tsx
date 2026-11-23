import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { OutputContractChangeSummary } from './OutputContractChangeSummary'

const contractChanges = [
  {
    trigger_id: 'child_trigger',
    trigger_name: 'Child invocation',
    changes: [
      {
        change_type: 'removed_output',
        field_path: 'release.tag',
        description: 'Removed output: release.tag',
        is_breaking: true,
      },
      {
        change_type: 'removed_output',
        field_path: 'release.url',
        description: 'Removed output: release.url',
        is_breaking: true,
      },
    ],
  },
]

const parentWorkflows = [
  {
    workflow_id: 'parent-workflow-id',
    workflow_name: 'Deploy parent',
    workflow_version: 3,
    step_id: 'invoke_release',
    step_name: 'Invoke release child',
  },
  {
    workflow_id: 'parent-workflow-id',
    workflow_name: 'Deploy parent',
    workflow_version: 3,
    step_id: 'invoke_preview',
    step_name: 'Invoke preview child',
  },
]

describe('OutputContractChangeSummary', () => {
  it('summarizes output and parent impact inline with expandable field details', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <OutputContractChangeSummary
        context="publish"
        contractChanges={contractChanges}
        parentWorkflows={parentWorkflows}
      />
    )

    expect(
      screen.getByText(
        'Output changes: Child invocation: Removed output: release.tag; Child invocation: Removed output: release.url. Published parent workflows will use the updated child version on their next run.'
      )
    ).toBeInTheDocument()
    expect(screen.getByText('1 visible published parent workflow')).toBeInTheDocument()
    expect(screen.getByText(/The count includes only parent workflows visible to you/)).toBeInTheDocument()
    expect(screen.queryByText('Child invocation: Removed output: release.tag')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Visible published parent workflows' })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()

    await user.click(screen.getByRole('button', { name: 'View all 2 output changes' }))
    expect(screen.getByText('Child invocation: Removed output: release.tag')).toBeInTheDocument()
    expect(screen.getByText('Child invocation: Removed output: release.url')).toBeInTheDocument()
  })

  it('does not show parent references for a draft-only save', () => {
    render(
      <OutputContractChangeSummary context="save" contractChanges={contractChanges} parentWorkflows={parentWorkflows} />
    )

    expect(
      screen.getByText(
        /Output changes: Child invocation: Removed output: release.tag; Child invocation: Removed output: release.url. Saving updates this draft only; published parent workflows continue using the latest published child version./
      )
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /visible parent workflows/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/Deploy parent/)).not.toBeInTheDocument()
  })

  it('shows trigger-removal details in the inline disclosure', async () => {
    const user = userEvent.setup()
    render(
      <OutputContractChangeSummary
        context="publish"
        contractChanges={[
          {
            trigger_id: 'child_trigger',
            trigger_name: 'Child trigger',
            changes: [
              {
                change_type: 'removed_trigger',
                field_path: 'child_trigger',
                description: 'Removed SubWorkflow Trigger: child_trigger',
                is_breaking: true,
              },
            ],
          },
        ]}
        parentWorkflows={[]}
      />
    )

    expect(
      screen.getByText('Output changes: Child trigger: Removed SubWorkflow Trigger: child_trigger.')
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View all 1 output changes' }))
    expect(screen.getByText('Child trigger: Removed SubWorkflow Trigger: child_trigger')).toBeInTheDocument()
  })

  it('uses visibility-scoped copy when no parent references are returned', () => {
    render(<OutputContractChangeSummary context="publish" contractChanges={contractChanges} parentWorkflows={[]} />)

    expect(screen.getByText('No visible published parent workflows are listed.')).toBeInTheDocument()
    expect(screen.getByText(/References outside your visibility scope may not be shown/)).toBeInTheDocument()
    expect(screen.queryByText(/0 visible published parent/)).not.toBeInTheDocument()
  })
})
