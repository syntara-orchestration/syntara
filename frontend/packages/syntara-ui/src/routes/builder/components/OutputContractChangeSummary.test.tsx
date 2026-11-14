import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { OutputContractChangeSummary } from './OutputContractChangeSummary'

describe('OutputContractChangeSummary', () => {
  it('shows contract changes and the published parent steps that reference the child', async () => {
    const { container } = render(
      <OutputContractChangeSummary
        contractChanges={[
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
            ],
          },
        ]}
        parentWorkflows={[
          {
            workflow_id: 'parent-workflow-id',
            workflow_name: 'Deploy parent',
            workflow_version: 3,
            step_id: 'invoke_release',
            step_name: 'Invoke release child',
          },
        ]}
      />
    )

    expect(screen.getByText('Removed output: release.tag')).toBeInTheDocument()
    expect(screen.getByText(/Deploy parent \(parent v3\).*Invoke release child/)).toBeInTheDocument()
    expect(
      screen.getByText(
        /If you publish these changes, each listed parent workflow will use the updated child version on its next run/
      )
    ).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('explains when there are no published parent references', () => {
    render(<OutputContractChangeSummary contractChanges={[]} parentWorkflows={[]} />)

    expect(screen.getByText('No published parent workflows currently reference this child.')).toBeInTheDocument()
  })
})
