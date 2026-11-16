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
  it('summarizes changes and opens the full visible parent-reference list on demand', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <OutputContractChangeSummary
        context="publish"
        contractChanges={contractChanges}
        parentWorkflows={parentWorkflows}
      />
    )

    expect(screen.getByText('Outputs removed: 2')).toBeInTheDocument()
    expect(screen.getByText('1 visible published parent workflows affected')).toBeInTheDocument()
    expect(screen.getByText('Removed output: release.tag')).not.toBeVisible()
    expect(await axe(container)).toHaveNoViolations()

    await user.click(screen.getByRole('button', { name: 'View details for 2 output changes' }))
    expect(screen.getByText('Removed output: release.tag')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'View visible parent workflows' }))
    expect(screen.getByRole('heading', { name: 'Visible published parent workflows' })).toBeInTheDocument()
    expect(
      screen.getByText(/Deploy parent \(parent v3\).*Invoke release child, Invoke preview child/)
    ).toBeInTheDocument()
    expect(screen.getAllByText(/References outside your visibility scope may not be listed/)).toHaveLength(2)
    expect(await axe(screen.getByRole('dialog', { name: 'Visible published parent workflows' }))).toHaveNoViolations()
  })

  it('does not show parent references for a draft-only save', () => {
    render(
      <OutputContractChangeSummary context="save" contractChanges={contractChanges} parentWorkflows={parentWorkflows} />
    )

    expect(screen.getByText(/Zero published parent workflows are affected/)).toBeInTheDocument()
    expect(screen.queryByText('View visible parent workflows')).not.toBeInTheDocument()
    expect(screen.queryByText(/Deploy parent/)).not.toBeInTheDocument()
  })

  it('uses visibility-scoped copy when no parent references are returned', () => {
    render(<OutputContractChangeSummary context="publish" contractChanges={contractChanges} parentWorkflows={[]} />)

    expect(screen.getByText(/No visible published parent workflows are listed/)).toBeInTheDocument()
    expect(screen.getByText(/References outside your visibility scope may not be shown/)).toBeInTheDocument()
  })
})
