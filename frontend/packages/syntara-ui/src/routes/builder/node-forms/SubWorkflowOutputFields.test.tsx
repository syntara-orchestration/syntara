import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { VersionViewContext } from '../VersionViewContext'

import { SubWorkflowOutputFields } from './SubWorkflowOutputFields'
import type { TriggerFormData } from './triggerFormSchema'

const mockWorkflowState = vi.hoisted(() => ({
  currentWorkflow: { workflow: { activities: [{ id: 'deploy', name: 'Deploy', type: 'script' }] } },
  edges: [{ source: 'trigger-0', target: 'deploy' }],
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: typeof mockWorkflowState) => unknown) => selector(mockWorkflowState),
}))
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (code: string) => void
    ariaLabel: string
  }) => <textarea aria-label={ariaLabel} value={code} onChange={(event) => onCodeChange(event.target.value)} />,
}))

function TestWrapper({
  outputSchema,
  outputMapping,
  outputFields = [],
  isVersionView = false,
  schemaError,
}: Readonly<{
  outputSchema: Record<string, unknown>
  outputMapping: Record<string, string>
  outputFields?: NonNullable<TriggerFormData['outputFields']>
  isVersionView?: boolean
  schemaError?: string
}>) {
  const methods = useForm<TriggerFormData>({
    defaultValues: {
      triggerType: 'subworkflow_trigger',
      outputSchema: JSON.stringify(outputSchema),
      outputMapping,
      outputFields,
    },
    errors: schemaError ? { outputSchema: { type: 'validate', message: schemaError } } : undefined,
  })

  return (
    <VersionViewContext.Provider value={isVersionView}>
      <FormProvider {...methods}>
        <SubWorkflowOutputFields triggerId="trigger-0" triggerIndex={0} />
        <FormValuesSummary />
      </FormProvider>
    </VersionViewContext.Provider>
  )
}

function FormValuesSummary() {
  const { control } = useFormContext<TriggerFormData>()
  const values = useWatch({ control })
  return <output aria-label="Current output contract">{JSON.stringify(values)}</output>
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

  it('preserves output schema and mappings when switching between Simple and Advanced', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper
        outputSchema={{
          type: 'object',
          properties: { status: { type: 'string', description: 'Deployment status' } },
        }}
        outputMapping={{ status: '${deploy.stdout}' }}
        outputFields={[
          {
            path: 'status',
            type: 'string',
            required: false,
            description: 'Deployment status',
            expression: '${deploy.stdout}',
          },
        ]}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    expect(screen.getByRole('button', { name: 'Advanced' })).toHaveAttribute('aria-pressed', 'true')
    let values = JSON.parse(screen.getByLabelText('Current output contract').textContent ?? '{}') as TriggerFormData
    expect(values.outputMapping).toEqual({ status: '${deploy.stdout}' })
    expect(JSON.parse(values.outputSchema ?? '{}')).toEqual({
      type: 'object',
      properties: { status: { type: 'string', description: 'Deployment status' } },
    })

    await user.click(screen.getByRole('button', { name: 'Simple' }))
    expect(screen.getByRole('button', { name: 'Simple' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Output name')).toHaveValue('status')
    values = JSON.parse(screen.getByLabelText('Current output contract').textContent ?? '{}') as TriggerFormData
    expect(values.outputMapping).toEqual({ status: '${deploy.stdout}' })
    expect(values.outputFields?.[0]).toEqual(
      expect.objectContaining({ path: 'status', expression: '${deploy.stdout}', description: 'Deployment status' })
    )
  })

  it('removes a mapping when its advanced source is cleared', async () => {
    const user = userEvent.setup()
    render(
      <TestWrapper
        outputSchema={{
          type: 'object',
          properties: { status: { type: 'string' } },
          allOf: [{ properties: { status: { minLength: 1 } } }],
        }}
        outputMapping={{ status: '${deploy.stdout}' }}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Clear selection' }))

    const values = JSON.parse(screen.getByLabelText('Current output contract').textContent ?? '{}') as TriggerFormData
    expect(values.outputMapping).toEqual({})
  })

  it('shows schema validation feedback in Advanced mode', async () => {
    render(
      <TestWrapper
        outputSchema={{
          type: 'object',
          properties: { status: { type: 'string' } },
          allOf: [{ properties: { status: { minLength: 1 } } }],
        }}
        outputMapping={{}}
        schemaError="Output schema is invalid"
      />
    )

    expect(await screen.findByText('Output schema is invalid')).toBeInTheDocument()
    expect(screen.queryByText(/Define the public fields the parent workflow can use/)).not.toBeInTheDocument()
  })

  it('disables both editors in version view', () => {
    render(
      <TestWrapper
        outputSchema={{ type: 'object', properties: { status: { type: 'string' } } }}
        outputMapping={{}}
        isVersionView
      />
    )

    expect(screen.getByRole('button', { name: 'Simple' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Advanced' })).toBeDisabled()
  })
})
