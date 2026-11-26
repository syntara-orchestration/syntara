import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { SubWorkflowOutputField } from '../utils/subWorkflowOutputContract'

import { SubWorkflowAdvancedMappings } from './SubWorkflowAdvancedMappings'

const workflowState = vi.hoisted(() => ({
  activities: [
    { id: 'route', name: 'Route', type: 'condition' },
    {
      id: 'deploy',
      name: 'Deploy',
      type: 'script',
      output_schema: [
        { name: 'stdout', type: 'number', description: 'Numeric result' },
        { name: 'payload', type: 'unknown', description: 'Open payload' },
      ],
    },
    { id: 'fallback', name: 'Fallback', type: 'script', output_schema: [] },
  ],
  edges: [
    { source: 'trigger-0', target: 'route' },
    { source: 'route', target: 'deploy', sourceHandle: 'success' },
    { source: 'route', target: 'fallback', sourceHandle: 'failure' },
  ],
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: unknown) => unknown) =>
    selector({ currentWorkflow: { workflow: { activities: workflowState.activities } }, edges: workflowState.edges }),
}))

beforeEach(() => {
  workflowState.activities = [
    { id: 'route', name: 'Route', type: 'condition' },
    {
      id: 'deploy',
      name: 'Deploy',
      type: 'script',
      output_schema: [
        { name: 'stdout', type: 'number', description: 'Numeric result' },
        { name: 'payload', type: 'unknown', description: 'Open payload' },
      ],
    },
    { id: 'fallback', name: 'Fallback', type: 'script', output_schema: [] },
  ]
  workflowState.edges = [
    { source: 'trigger-0', target: 'route' },
    { source: 'route', target: 'deploy', sourceHandle: 'true' },
    { source: 'route', target: 'fallback', sourceHandle: 'false' },
  ]
})

const fields: SubWorkflowOutputField[] = [
  { path: 'status', type: 'string', required: true, description: 'Public status' },
  { path: 'legacy', type: 'string', required: false },
  { path: 'detail', type: 'object', required: false },
]

describe('SubWorkflowAdvancedMappings', () => {
  it('edits the mapping for a declared output field', async () => {
    const user = userEvent.setup()
    const onMappingChange = vi.fn()
    const { container } = render(
      <SubWorkflowAdvancedMappings
        fields={[{ path: 'release.tag', type: 'string', required: true, description: 'Published tag' }]}
        outputMapping={{}}
        triggerId="trigger-0"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={onMappingChange}
      />
    )

    const mapping = screen.getByRole('textbox', { name: 'Type to filter' })
    expect(mapping).toHaveAttribute('aria-required', 'true')
    expect(screen.getByText('release.tag', { exact: true })).toBeInTheDocument()
    await user.click(mapping)
    await user.click(screen.getByRole('option', { name: 'stdout Numeric result' }))

    expect(onMappingChange).toHaveBeenLastCalledWith('release.tag', '${deploy.stdout}')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('explains missing schema fields accessibly when there is nothing to map', async () => {
    const { container } = render(
      <SubWorkflowAdvancedMappings
        fields={[]}
        outputMapping={{}}
        triggerId="trigger-0"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={vi.fn()}
      />
    )

    expect(screen.getByText('Add output fields to the schema above to map their values')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('explains how to configure child outputs when there are no source choices', async () => {
    const user = userEvent.setup()
    workflowState.activities = []
    workflowState.edges = []
    render(
      <SubWorkflowAdvancedMappings
        fields={[{ path: 'release.tag', type: 'string', required: true, description: '' }]}
        outputMapping={{}}
        triggerId="trigger-0"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={vi.fn()}
      />
    )

    await user.click(screen.getByRole('textbox', { name: 'Type to filter' }))
    expect(
      screen.getByRole('option', {
        name: 'No child step outputs are available yet. Add a reachable child step with outputs to map this field.',
      })
    ).toBeInTheDocument()
  })

  it('shows source reachability, type mismatch, and unavailable mapping feedback', () => {
    render(
      <SubWorkflowAdvancedMappings
        fields={fields}
        outputMapping={{ status: '${deploy.stdout}', legacy: '${deleted_step.stdout}' }}
        triggerId="trigger-0"
        triggerIndex={0}
        isVersionView={false}
        onMappingChange={vi.fn()}
      />
    )

    expect(screen.getByText('Source step may not execute on every workflow path.')).toBeInTheDocument()
    expect(
      screen.getByText(
        'The declared type (string) differs from the selected source type (number). Review the output schema.'
      )
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'This saved source is unavailable in the current workflow. Choose an existing child step output.'
      )
    ).toBeInTheDocument()
    expect(screen.getByText('Description: Public status')).toBeInTheDocument()
    expect(screen.getAllByText('Description: No description')).toHaveLength(2)
  })

  it('identifies dynamic descendants and disables source selection in version view', () => {
    render(
      <SubWorkflowAdvancedMappings
        fields={[fields[2]]}
        outputMapping={{ detail: '${deploy.payload.owner}' }}
        triggerId="trigger-0"
        triggerIndex={0}
        isVersionView
        onMappingChange={vi.fn()}
      />
    )

    expect(screen.getByText('Resolved at runtime; the child run fails if this path is missing.')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Type to filter' })).toBeDisabled()
  })
})
