import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SubWorkflowSimpleOutputFields } from './SubWorkflowSimpleOutputFields'
import type { TriggerFormData } from './triggerFormSchema'

const mockWorkflowState = vi.hoisted(() => ({
  currentWorkflow: { workflow: { activities: [{ id: 'deploy', name: 'Deploy', type: 'script' }] } },
  edges: [{ source: 'trigger-0', target: 'deploy' }],
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: typeof mockWorkflowState) => unknown) => selector(mockWorkflowState),
}))

function TestWrapper() {
  const methods = useForm<TriggerFormData>({ defaultValues: { outputFields: [] } })
  return (
    <FormProvider {...methods}>
      <SubWorkflowSimpleOutputFields triggerId="child-trigger" triggerIndex={0} isVersionView={false} />
    </FormProvider>
  )
}

describe('SubWorkflowSimpleOutputFields', () => {
  it('adds editable output fields and lists typed child step output sources', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    await user.click(screen.getByRole('button', { name: 'Add output field' }))

    expect(screen.getByRole('textbox', { name: 'Name returned to parent' })).toBeInTheDocument()
    await user.click(screen.getByRole('textbox', { name: 'Type to filter' }))
    expect(screen.getByText('Deploy')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /status/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /^stdout Standard output/ })).toBeInTheDocument()
  })

  it('has no accessibility violations in the empty state', async () => {
    const { container } = render(<TestWrapper />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
