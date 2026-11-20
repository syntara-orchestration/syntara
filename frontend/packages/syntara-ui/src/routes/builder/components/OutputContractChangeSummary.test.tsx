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
  it('focuses on publish impact and opens visible parent references on demand', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <OutputContractChangeSummary
        context="publish"
        contractChanges={contractChanges}
        parentWorkflows={parentWorkflows}
      />
    )

    expect(screen.getByText('The child workflow’s declared output contract is changing.')).toBeInTheDocument()
    expect(
      screen.getByText('Published parent workflows will use the updated child version on their next run.')
    ).toBeInTheDocument()
    expect(screen.getByText('1 visible published parent workflow')).toBeInTheDocument()
    expect(screen.queryByText('Removed output: release.tag')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /view details for/i })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()

    await user.click(screen.getByRole('button', { name: 'View visible parent workflows' }))
    expect(screen.getByRole('heading', { name: 'Visible published parent workflows' })).toBeInTheDocument()
    expect(
      screen.getByText(/Deploy parent \(parent v3\).*Invoke release child, Invoke preview child/)
    ).toBeInTheDocument()
    expect(screen.getByText(/References outside your visibility scope may not be listed/)).toBeInTheDocument()
    expect(await axe(screen.getByRole('dialog', { name: 'Visible published parent workflows' }))).toHaveNoViolations()
  })

  it('does not show parent references for a draft-only save', () => {
    render(
      <OutputContractChangeSummary context="save" contractChanges={contractChanges} parentWorkflows={parentWorkflows} />
    )

    expect(
      screen.getByText(
        /Saving updates this draft only. Published parent workflows continue using the latest published child version./
      )
    ).toBeInTheDocument()
    expect(screen.queryByText('View visible parent workflows')).not.toBeInTheDocument()
    expect(screen.queryByText(/Deploy parent/)).not.toBeInTheDocument()
  })

  it('keeps field-level output details out of the confirmation summary', () => {
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

    expect(screen.getByText('The child workflow’s declared output contract is changing.')).toBeInTheDocument()
    expect(screen.queryByText('Removed SubWorkflow Trigger: child_trigger')).not.toBeInTheDocument()
  })

  it('uses visibility-scoped copy when no parent references are returned', () => {
    render(<OutputContractChangeSummary context="publish" contractChanges={contractChanges} parentWorkflows={[]} />)

    expect(screen.getByText(/No visible published parent workflows are listed/)).toBeInTheDocument()
    expect(screen.getByText(/References outside your visibility scope may not be shown/)).toBeInTheDocument()
  })
})
