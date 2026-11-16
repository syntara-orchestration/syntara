import { render, screen } from '@testing-library/react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'

import { SubWorkflowTriggerFields } from './SubWorkflowTriggerFields'
import type { TriggerFormData } from './triggerFormSchema'

// Mock the code editor to avoid Monaco setup in tests
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({ code, ariaLabel }: { code: string; ariaLabel: string }) => (
    <div data-testid="code-editor" aria-label={ariaLabel}>
      {code || 'empty'}
    </div>
  ),
}))

vi.mock('../components/JsonEditorToolbar', () => ({
  JsonEditorControls: () => <div data-testid="json-editor-controls">Controls</div>,
}))

vi.mock('./SubWorkflowOutputFields', () => ({
  SubWorkflowOutputFields: () => <div data-testid="subworkflow-output-fields">Output fields</div>,
}))

function TestWrapper({ children, inputSchemaError }: { children: React.ReactNode; inputSchemaError?: string }) {
  const methods = useForm<TriggerFormData>({
    defaultValues: { inputSchema: '', outputSchema: '' },
    errors: inputSchemaError ? { inputSchema: { type: 'validate', message: inputSchemaError } } : undefined,
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

describe('SubWorkflowTriggerFields', () => {
  it('renders the info callout and input schema editor', () => {
    render(
      <TestWrapper>
        <SubWorkflowTriggerFields triggerId="trigger-0" triggerIndex={0} />
      </TestWrapper>
    )

    expect(screen.getByText(/can be called from another workflow/i)).toBeInTheDocument()
    expect(screen.getByText('Workflow trigger')).toBeInTheDocument()
    expect(screen.getByText('Input schema')).toBeInTheDocument()
    expect(screen.getByTestId('code-editor')).toBeInTheDocument()
  })

  it('renders the returned outputs section', () => {
    render(
      <TestWrapper>
        <SubWorkflowTriggerFields triggerId="trigger-0" triggerIndex={0} />
      </TestWrapper>
    )

    expect(screen.getByText('Returned outputs')).toBeInTheDocument()
    expect(
      screen.getByText(/Define the values this workflow returns by mapping each public output field/)
    ).toBeInTheDocument()
  })

  it('renders the output fields component', () => {
    render(
      <TestWrapper>
        <SubWorkflowTriggerFields triggerId="trigger-0" triggerIndex={0} />
      </TestWrapper>
    )

    expect(screen.getByTestId('subworkflow-output-fields')).toBeInTheDocument()
  })

  it('shows input schema validation feedback instead of the optional schema hint', () => {
    render(
      <TestWrapper inputSchemaError="Input schema is invalid">
        <SubWorkflowTriggerFields triggerId="trigger-0" triggerIndex={0} />
      </TestWrapper>
    )

    expect(screen.getByText('Input schema is invalid')).toBeInTheDocument()
    expect(
      screen.queryByText('Optional JSON Schema defining the input data required to run this workflow.')
    ).not.toBeInTheDocument()
  })
})
