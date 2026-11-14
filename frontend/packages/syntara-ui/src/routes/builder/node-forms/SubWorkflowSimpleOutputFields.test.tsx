import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SubWorkflowSimpleOutputFields } from './SubWorkflowSimpleOutputFields'
import type { TriggerFormData } from './triggerFormSchema'

const mockWorkflowState = vi.hoisted(() => ({
  currentWorkflow: { workflow: { activities: [] as Array<{ id: string; name: string; type: string }> } },
  edges: [] as Array<{ source: string; target: string; sourceHandle?: string | null }>,
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: typeof mockWorkflowState) => unknown) => selector(mockWorkflowState),
}))

function TestWrapper({ outputFields = [] }: Readonly<{ outputFields?: NonNullable<TriggerFormData['outputFields']> }>) {
  const methods = useForm<TriggerFormData>({ defaultValues: { outputFields } })
  return (
    <FormProvider {...methods}>
      <SubWorkflowSimpleOutputFields
        triggerId="child-trigger"
        triggerIndex={0}
        isVersionView={false}
        onRowsChange={vi.fn()}
      />
    </FormProvider>
  )
}

describe('SubWorkflowSimpleOutputFields', () => {
  beforeEach(() => {
    mockWorkflowState.currentWorkflow.workflow.activities = [{ id: 'deploy', name: 'Deploy', type: 'script' }]
    mockWorkflowState.edges = [{ source: 'trigger-0', target: 'deploy' }]
  })

  it('adds editable output fields and lists typed child step output sources', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByRole('button', { name: 'Add output field' }))

    expect(screen.getByRole('textbox', { name: 'Output name' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Required output' })).not.toBeChecked()
    expect(
      screen.getByText(
        'Required marks this value as part of the output contract. Workflow routing determines whether its source step runs.'
      )
    ).toBeInTheDocument()
    await user.click(screen.getByRole('textbox', { name: 'Type to filter' }))
    expect(screen.getByText('Deploy')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /status/ })).toBeInTheDocument()
    const standardOutput = screen.getByRole('option', { name: /^stdout Standard output/ })
    expect(standardOutput).toBeInTheDocument()
    await user.click(standardOutput)
    await user.click(screen.getByRole('button', { name: 'Field options' }))
    expect(screen.getByRole('textbox', { name: 'Description (optional)' })).toHaveValue(
      'Help parent workflow authors understand this value'
    )
  })

  it('shows an unavailable state for a saved mapping whose source step was removed', () => {
    render(
      <TestWrapper
        outputFields={[
          { path: 'release.tag', type: 'string', required: false, description: '', expression: '${removed.stdout}' },
        ]}
      />
    )

    expect(screen.getByRole('textbox', { name: 'Type to filter' })).toHaveValue('Unavailable in current workflow')
    expect(screen.getByText(/This saved source is unavailable/)).toBeInTheDocument()
  })

  it('warns when a required output maps to a conditionally run step', () => {
    mockWorkflowState.currentWorkflow.workflow.activities = [
      { id: 'condition', name: 'Check condition', type: 'condition' },
      { id: 'deploy', name: 'Deploy', type: 'script' },
      { id: 'skip', name: 'Skip deploy', type: 'script' },
    ]
    mockWorkflowState.edges = [
      { source: 'trigger-0', target: 'condition' },
      { source: 'condition', target: 'deploy', sourceHandle: 'true' },
      { source: 'condition', target: 'skip', sourceHandle: 'false' },
    ]
    render(
      <TestWrapper
        outputFields={[
          { path: 'deployment.url', type: 'string', required: true, description: '', expression: '${deploy.stdout}' },
        ]}
      />
    )

    expect(screen.getByText(/This step may not run on every path/)).toBeInTheDocument()
    expect(screen.getByText(/If this required value is missing, the child run fails/)).toBeInTheDocument()
  })

  it('has no accessibility violations in the empty state', async () => {
    const { container } = render(<TestWrapper />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
