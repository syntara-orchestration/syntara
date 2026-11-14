import { render, screen } from '@testing-library/react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SubWorkflowOutputFields } from './SubWorkflowOutputFields'
import type { TriggerFormData } from './triggerFormSchema'

const mockWorkflowState = vi.hoisted(() => ({
  currentWorkflow: { workflow: { activities: [{ id: 'deploy', name: 'Deploy', type: 'script' }] } },
  edges: [{ source: 'trigger-0', target: 'deploy' }],
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: typeof mockWorkflowState) => unknown) => selector(mockWorkflowState),
}))
vi.mock('../components/ExpandableCodeEditor', () => ({ ExpandableCodeEditor: () => null }))

function TestWrapper({
  outputSchema,
  outputMapping,
}: Readonly<{ outputSchema: Record<string, unknown>; outputMapping: Record<string, string> }>) {
  const methods = useForm<TriggerFormData>({
    defaultValues: {
      triggerType: 'subworkflow_trigger',
      outputSchema: JSON.stringify(outputSchema),
      outputMapping,
      outputFields: [],
    },
  })

  return (
    <FormProvider {...methods}>
      <SubWorkflowOutputFields triggerId="trigger-0" triggerIndex={0} />
    </FormProvider>
  )
}

describe('SubWorkflowOutputFields', () => {
  it('keeps composed schemas in Advanced mode and explains why Simple mode is unavailable', async () => {
    const { container } = render(
      <TestWrapper
        outputSchema={{
          type: 'object',
          properties: { release: { type: 'string' } },
          allOf: [{ properties: { release: { minLength: 1 } } }],
        }}
        outputMapping={{ release: '${deploy.stdout}' }}
      />
    )

    expect(screen.getByRole('button', { name: 'Advanced' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Simple' })).toBeDisabled()
    expect(screen.getByText(/Simple mode cannot represent every schema feature or mapping/)).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('keeps mappings to nested object values in Advanced mode', () => {
    render(
      <TestWrapper
        outputSchema={{
          type: 'object',
          properties: { release: { type: 'object', properties: { tag: { type: 'string' } } } },
        }}
        outputMapping={{ release: '${deploy.stdout_json}' }}
      />
    )

    expect(screen.getByRole('button', { name: 'Advanced' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Simple' })).toBeDisabled()
  })
})
