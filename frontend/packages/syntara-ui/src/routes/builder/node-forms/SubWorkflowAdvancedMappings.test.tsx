import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SubWorkflowAdvancedMappings } from './SubWorkflowAdvancedMappings'

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: { currentWorkflow: null; edges: [] }) => unknown) =>
    selector({ currentWorkflow: null, edges: [] }),
}))

describe('SubWorkflowAdvancedMappings', () => {
  it('edits the mapping for each declared output field', async () => {
    const user = userEvent.setup()
    const onMappingChange = vi.fn()
    render(
      <SubWorkflowAdvancedMappings
        fields={[{ path: 'release.tag', type: 'string', required: true, description: 'Published tag' }]}
        outputMapping={{}}
        triggerId="trigger"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={onMappingChange}
      />
    )

    await user.type(screen.getByLabelText('release.tag (string) — Required'), 'x')

    expect(onMappingChange).toHaveBeenLastCalledWith('release.tag', 'x')
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
        'Choose the child step output that supplies each declared field. The value is available if that step runs.'
      )
    ).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
