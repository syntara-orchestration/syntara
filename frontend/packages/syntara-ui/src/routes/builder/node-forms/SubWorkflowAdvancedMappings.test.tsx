import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SubWorkflowAdvancedMappings } from './SubWorkflowAdvancedMappings'

const mockWorkflowState = vi.hoisted(() => ({
  currentWorkflow: {
    workflow: { activities: [{ id: 'deploy', name: 'Deploy', type: 'script' }] },
  },
  edges: [{ source: 'trigger-0', target: 'deploy' }],
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: typeof mockWorkflowState) => unknown) => selector(mockWorkflowState),
}))

describe('SubWorkflowAdvancedMappings', () => {
  it('edits the mapping for each declared output field', async () => {
    const user = userEvent.setup()
    const onMappingChange = vi.fn()
    const { container } = render(
      <SubWorkflowAdvancedMappings
        fields={[{ path: 'release.tag', type: 'string', required: true, description: 'Published tag' }]}
        outputMapping={{}}
        triggerId="trigger"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={onMappingChange}
      />
    )

    const mapping = screen.getByRole('textbox', { name: 'Type to filter' })
    expect(mapping).toHaveAttribute('aria-required', 'true')
    expect(screen.getByText('release.tag', { exact: true })).toBeInTheDocument()
    expect(screen.queryByText('release.tag (string)', { exact: true })).not.toBeInTheDocument()
    expect(screen.getByText('*', { exact: true })).toBeInTheDocument()
    await user.click(mapping)
    await user.click(screen.getByRole('option', { name: /^stdout Standard output/ }))

    expect(onMappingChange).toHaveBeenLastCalledWith('release.tag', '${deploy.stdout}')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('warns when an advanced mapping references an output with a different declared type', () => {
    render(
      <SubWorkflowAdvancedMappings
        fields={[{ path: 'release.code', type: 'string', required: false }]}
        outputMapping={{ 'release.code': '${deploy.return_code}' }}
        triggerId="trigger-0"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={vi.fn()}
      />
    )

    const mapping = screen.getByRole('textbox', { name: 'Type to filter' })
    expect(mapping).not.toHaveAttribute('aria-required')
    expect(screen.queryByText('*', { exact: true })).not.toBeInTheDocument()
    expect(screen.getByText(/declared type \(string\) differs from the selected source type \(number\)/)).toBeVisible()
  })

  it('warns when a saved source output no longer exists', () => {
    render(
      <SubWorkflowAdvancedMappings
        fields={[{ path: 'release.tag', type: 'string', required: false }]}
        outputMapping={{ 'release.tag': '${deploy.deleted_output}' }}
        triggerId="trigger-0"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={vi.fn()}
      />
    )

    expect(screen.getByText(/This saved source is unavailable in the current workflow/)).toBeVisible()
  })

  it('has no accessibility violations in the empty state', async () => {
    const { container } = render(
      <SubWorkflowAdvancedMappings
        fields={[]}
        outputMapping={{}}
        triggerId="trigger"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={vi.fn()}
      />
    )

    expect(
      screen.getByText(
        'Required outputs are part of the child workflow’s return contract. If routing skips a required output’s source step, the child run fails. Optional outputs from skipped steps are omitted.'
      )
    ).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
