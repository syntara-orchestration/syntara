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
        field_path: 'legacy_status',
        old_type: 'string',
        description: 'Removed output: legacy_status',
        is_breaking: true,
      },
      {
        change_type: 'mapping_changed',
        field_path: 'legacy_status',
        description: 'Changed the source mapping for output: legacy_status',
        is_breaking: false,
      },
    ],
  },
]

const breakingChanges = [
  {
    trigger_id: 'child_trigger',
    trigger_name: 'Child invocation',
    changes: [contractChanges[0].changes[0]],
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
  it('summarizes a breaking removal without repeating its mapping change', async () => {
    const { container } = render(
      <OutputContractChangeSummary
        context="publish"
        contractChanges={contractChanges}
        breakingChanges={breakingChanges}
        hasBreakingChanges
        parentWorkflows={parentWorkflows}
      />
    )

    expect(
      screen.getByText(
        'This version removes the output “legacy_status”. Published parent workflows will use the updated child version on their next run.'
      )
    ).toBeInTheDocument()
    expect(screen.getByText('Used by 1 visible published workflow')).toBeInTheDocument()
    expect(screen.queryByText(/source mapping/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'View output change details' })).not.toBeInTheDocument()
    expect(screen.queryByText(/The count includes only parent workflows visible to you/)).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Visible published parent workflows' })).not.toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('does not show parent references for a draft-only save', () => {
    render(
      <OutputContractChangeSummary context="save" contractChanges={contractChanges} parentWorkflows={parentWorkflows} />
    )

    expect(
      screen.getByText(
        /This draft removes the output “legacy_status”. Saving updates this draft only; published parent workflows continue using the latest published child version./
      )
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /visible parent workflows/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/Deploy parent/)).not.toBeInTheDocument()
  })

  it('shows old and new output types in the inline disclosure', async () => {
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
                change_type: 'type_change',
                field_path: 'release.version',
                old_type: 'string',
                new_type: 'integer',
                description: 'Type changed: release.version (string → integer)',
                is_breaking: true,
              },
            ],
          },
        ]}
        breakingChanges={[
          {
            trigger_id: 'child_trigger',
            trigger_name: 'Child trigger',
            changes: [
              {
                change_type: 'type_change',
                field_path: 'release.version',
                old_type: 'string',
                new_type: 'integer',
                description: 'Type changed: release.version (string → integer)',
                is_breaking: true,
              },
            ],
          },
        ]}
        hasBreakingChanges
        parentWorkflows={[]}
      />
    )

    expect(
      screen.getByText(
        'This version changes the type of the output “release.version”. Published parent workflows will use the updated child version on their next run.'
      )
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View output change details' }))
    expect(screen.getByText('Child trigger: Type changed: release.version (string → integer)')).toBeInTheDocument()
  })

  it('uses visibility-scoped copy when no parent references are returned', () => {
    render(<OutputContractChangeSummary context="publish" contractChanges={contractChanges} parentWorkflows={[]} />)

    expect(screen.getByText(/No visible published parent workflows are listed/)).toBeInTheDocument()
    expect(screen.getByText(/References outside your visibility scope may not be shown/)).toBeInTheDocument()
    expect(screen.queryByText(/0 visible published parent/)).not.toBeInTheDocument()
  })

  it('describes root-level constraint changes without exposing the internal path sentinel', () => {
    render(
      <OutputContractChangeSummary
        context="publish"
        contractChanges={[
          {
            trigger_id: 'child_trigger',
            trigger_name: 'Child trigger',
            changes: [
              {
                change_type: 'constraint_change',
                field_path: '$root',
                description: 'Output validation constraints changed: $root',
                is_breaking: true,
              },
            ],
          },
        ]}
        parentWorkflows={[]}
      />
    )

    expect(screen.getByText(/This version changes root-level validation constraints/)).toBeInTheDocument()
    expect(screen.queryByText(/“\$root”/)).not.toBeInTheDocument()
  })
})
