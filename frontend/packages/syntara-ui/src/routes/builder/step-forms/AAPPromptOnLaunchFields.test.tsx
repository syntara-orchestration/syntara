import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import { PromptOnLaunchFields } from './AAPPromptOnLaunchFields'

// Mock ExpandableCodeEditor to use a simple textarea for testing
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    onBlur,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (code: string) => void
    onBlur?: (value: string) => void
    ariaLabel?: string
  }) => (
    <textarea
      data-testid="extra-vars-editor"
      id="aap-extra_vars"
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
      onBlur={(e) => onBlur?.(e.currentTarget.value)}
      placeholder='{"version": "1.0", "environment": "prod"}'
      aria-label={ariaLabel}
    />
  ),
}))

function TestWrapper({
  children,
  defaultValues,
}: {
  children: React.ReactNode
  defaultValues?: Partial<AAPJobTemplateFormData>
}) {
  const methods = useForm<AAPJobTemplateFormData>({
    defaultValues: {
      name: '',
      organization_name: '',
      job_template_name: '',
      inventory_name: '',
      extra_vars: '',
      limit: '',
      tags: '',
      skip_tags: '',
      verbosity: '',
      job_type: '',
      diff_mode: false,
      job_credentials: [],
      ...defaultValues,
    },
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

const mockInventories = [
  { id: 1, name: 'Demo Inventory', description: 'Demo hosts' },
  { id: 2, name: 'Production', description: 'Prod hosts' },
]

const mockExecutionEnvironments = [
  { id: 1, name: 'Default EE', description: 'Default execution environment' },
  { id: 2, name: 'Custom EE', description: 'Custom EE with extra collections' },
]

const mockCredentials = [
  { id: 1, name: 'Machine Credential', description: 'SSH key for hosts' },
  { id: 2, name: 'AWS Credential', description: 'AWS access keys' },
]

const mockInstanceGroups = [
  { id: 1, name: 'default' },
  { id: 2, name: 'controlplane' },
]

const mockLabels = [
  { id: 1, name: 'Production' },
  { id: 2, name: 'Critical' },
]

const defaultTemplateDetail = {
  id: 10,
  name: 'Deploy App',
  description: 'Deploy the application',
  ask_job_type_on_launch: false,
  ask_inventory_on_launch: false,
  ask_credential_on_launch: false,
  ask_variables_on_launch: false,
  ask_limit_on_launch: false,
  ask_tags_on_launch: false,
  ask_skip_tags_on_launch: false,
  ask_verbosity_on_launch: false,
  ask_diff_mode_on_launch: false,
  ask_forks_on_launch: false,
  ask_job_slice_count_on_launch: false,
  ask_execution_environment_on_launch: false,
  ask_instance_groups_on_launch: false,
  ask_labels_on_launch: false,
  ask_timeout_on_launch: false,
  survey_enabled: false,
  url: 'https://aap.example.com/execution/templates/job-template/10/details',
  default_labels: [] as Array<{ id: number; name: string }>,
}

describe('AAPPromptOnLaunchFields', () => {
  let mockTemplateDetail: typeof defaultTemplateDetail

  beforeEach(() => {
    vi.clearAllMocks()
    mockTemplateDetail = { ...defaultTemplateDetail }
  })

  it('renders nothing when no prompt-on-launch flags are enabled', () => {
    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument()
  })

  it('renders "Prompt on Launch" section title when at least one flag is enabled', () => {
    mockTemplateDetail.ask_variables_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByText('Prompt on Launch')).toBeInTheDocument()
  })

  it('renders extra vars field when ask_variables_on_launch is true', () => {
    mockTemplateDetail.ask_variables_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Extra Variables')).toBeInTheDocument()
  })

  it('renders inventory field when ask_inventory_on_launch is true', () => {
    mockTemplateDetail.ask_inventory_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByPlaceholderText(/No default inventory/i)).toBeInTheDocument()
  })

  it('renders credentials field when ask_credential_on_launch is true', () => {
    mockTemplateDetail.ask_credential_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={mockCredentials}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByRole('button', { name: /No default credentials/i })).toBeInTheDocument()
  })

  it('renders execution environment field when ask_execution_environment_on_launch is true', () => {
    mockTemplateDetail.ask_execution_environment_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={mockExecutionEnvironments}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByPlaceholderText(/No default execution environment/i)).toBeInTheDocument()
  })

  it('renders instance groups field when ask_instance_groups_on_launch is true', () => {
    mockTemplateDetail.ask_instance_groups_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={mockInstanceGroups}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByPlaceholderText(/Use default instance groups/i)).toBeInTheDocument()
  })

  it('renders limit field when ask_limit_on_launch is true', () => {
    mockTemplateDetail.ask_limit_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Limit')).toBeInTheDocument()
  })

  it('renders tags field when ask_tags_on_launch is true', () => {
    mockTemplateDetail.ask_tags_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Job tags')).toBeInTheDocument()
  })

  it('renders skip tags field when ask_skip_tags_on_launch is true', () => {
    mockTemplateDetail.ask_skip_tags_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Skip tags')).toBeInTheDocument()
  })

  it('renders verbosity field when ask_verbosity_on_launch is true', () => {
    mockTemplateDetail.ask_verbosity_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Verbosity')).toBeInTheDocument()
  })

  it('renders job type field when ask_job_type_on_launch is true', () => {
    mockTemplateDetail.ask_job_type_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Run type')).toBeInTheDocument()
  })

  it('renders diff mode field when ask_diff_mode_on_launch is true', () => {
    mockTemplateDetail.ask_diff_mode_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Show changes')).toBeInTheDocument()
  })

  it('renders forks field when ask_forks_on_launch is true', () => {
    mockTemplateDetail.ask_forks_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Forks')).toBeInTheDocument()
  })

  it('renders job slicing field when ask_job_slice_count_on_launch is true', () => {
    mockTemplateDetail.ask_job_slice_count_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Job slicing')).toBeInTheDocument()
  })

  it('renders labels field when ask_labels_on_launch is true', () => {
    mockTemplateDetail.ask_labels_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByRole('button', { name: /select or create labels/i })).toBeInTheDocument()
  })

  it('displays default labels when template provides them', () => {
    mockTemplateDetail.ask_labels_on_launch = true
    mockTemplateDetail.default_labels = [
      { id: 1, name: 'Production' },
      { id: 2, name: 'Critical' },
    ]

    render(
      <TestWrapper defaultValues={{ labels: ['Production', 'Critical'] }}>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={mockLabels}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    // Verify the labels field is rendered and shows default labels as chips
    expect(screen.getByText('Production')).toBeInTheDocument()
    expect(screen.getByText('Critical')).toBeInTheDocument()
  })

  it('allows selecting verbosity level', async () => {
    const user = userEvent.setup()
    mockTemplateDetail.ask_verbosity_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const verbosityToggle = screen.getByRole('button', { name: 'Verbosity' })
    await user.click(verbosityToggle)
    await user.click(screen.getByRole('option', { name: '2 - More Verbose' }))

    expect(verbosityToggle).toHaveTextContent('2 - More Verbose')
  })

  it('toggles diff mode switch', async () => {
    const user = userEvent.setup()
    mockTemplateDetail.ask_diff_mode_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const diffModeSwitch = screen.getByRole('switch', { name: 'Show changes' })
    expect(diffModeSwitch).not.toBeChecked()

    await user.click(diffModeSwitch)
    expect(diffModeSwitch).toBeChecked()
  })

  it('allows typing in extra vars textarea', async () => {
    const user = userEvent.setup()
    mockTemplateDetail.ask_variables_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const extraVarsInput = screen.getByPlaceholderText(/version/i)
    await user.click(extraVarsInput)
    await user.paste('{"key": "value"}')

    expect(extraVarsInput).toHaveValue('{"key": "value"}')
  })

  it('renders multiple fields when multiple flags are enabled', () => {
    mockTemplateDetail.ask_variables_on_launch = true
    mockTemplateDetail.ask_limit_on_launch = true
    mockTemplateDetail.ask_verbosity_on_launch = true
    mockTemplateDetail.ask_diff_mode_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByLabelText('Extra Variables')).toBeInTheDocument()
    expect(screen.getByLabelText('Limit')).toBeInTheDocument()
    expect(screen.getByLabelText('Verbosity')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Show changes' })).toBeInTheDocument()
  })

  it('calls search callbacks when typeahead inputs change', async () => {
    const user = userEvent.setup()
    const onSearchInventories = vi.fn()
    mockTemplateDetail.ask_inventory_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={onSearchInventories}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const inventoryInput = screen.getByPlaceholderText(/No default inventory/i)
    await user.click(inventoryInput)
    await user.type(inventoryInput, 'prod')

    await waitFor(() => {
      expect(onSearchInventories).toHaveBeenCalledWith('prod')
    })
  })

  it('has no accessibility violations', async () => {
    mockTemplateDetail.ask_variables_on_launch = true
    mockTemplateDetail.ask_limit_on_launch = true
    mockTemplateDetail.ask_verbosity_on_launch = true
    mockTemplateDetail.ask_diff_mode_on_launch = true
    mockTemplateDetail.ask_inventory_on_launch = true
    mockTemplateDetail.ask_credential_on_launch = true

    const { container } = render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          executionEnvironments={mockExecutionEnvironments}
          loadingExecutionEnvironments={false}
          credentials={mockCredentials}
          loadingCredentials={false}
          instanceGroups={mockInstanceGroups}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders nothing when templateDetail is undefined', () => {
    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={undefined}
          isLoadingDetail={false}
        />
      </TestWrapper>
    )

    expect(screen.queryByText('Prompt on Launch')).not.toBeInTheDocument()
  })

  it('renders nothing when isLoadingDetail is true', () => {
    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={true}
        />
      </TestWrapper>
    )

    expect(screen.queryByText('Prompt on Launch')).not.toBeInTheDocument()
  })

  it('uses default noop callbacks when onSearch callbacks are not provided', () => {
    mockTemplateDetail.ask_inventory_on_launch = true

    // Should not throw when search callbacks are not provided
    expect(() => {
      render(
        <TestWrapper>
          <PromptOnLaunchFields
            extraVarsEditorRef={{ current: null }}
            templateDetail={mockTemplateDetail}
            inventories={mockInventories}
          />
        </TestWrapper>
      )
    }).not.toThrow()

    expect(screen.getByPlaceholderText(/No default inventory/i)).toBeInTheDocument()
  })

  it('calls onSearchExecutionEnvironments when execution environment search changes', async () => {
    const user = userEvent.setup()
    const onSearchExecutionEnvironments = vi.fn()
    mockTemplateDetail.ask_execution_environment_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={mockExecutionEnvironments}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={onSearchExecutionEnvironments}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const eeInput = screen.getByPlaceholderText(/No default execution environment/i)
    await user.click(eeInput)
    await user.type(eeInput, 'custom')

    await waitFor(() => {
      expect(onSearchExecutionEnvironments).toHaveBeenCalledWith('custom')
    })
  })

  it('calls onSearchCredentials when credentials search changes', async () => {
    const user = userEvent.setup()
    const onSearchCredentials = vi.fn()
    mockTemplateDetail.ask_credential_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={mockCredentials}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={onSearchCredentials}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /No default credentials/i })
    await user.click(toggle)

    const searchInput = screen.getByPlaceholderText('Search')
    await user.type(searchInput, 'aws')

    await waitFor(
      () => {
        expect(onSearchCredentials).toHaveBeenCalledWith('aws')
      },
      { timeout: 500 }
    )
  })

  it('calls onSearchInstanceGroups when instance groups search changes', async () => {
    const user = userEvent.setup()
    const onSearchInstanceGroups = vi.fn()
    mockTemplateDetail.ask_instance_groups_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={mockInstanceGroups}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={onSearchInstanceGroups}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const igInput = screen.getByPlaceholderText(/Use default instance groups/i)
    await user.click(igInput)
    await user.type(igInput, 'control')

    await waitFor(() => {
      expect(onSearchInstanceGroups).toHaveBeenCalledWith('control')
    })
  })

  it('calls onSearchLabels when labels search changes', async () => {
    const user = userEvent.setup()
    const onSearchLabels = vi.fn()
    mockTemplateDetail.ask_labels_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={mockLabels}
          loadingLabels={false}
          onSearchLabels={onSearchLabels}
        />
      </TestWrapper>
    )

    const toggle = screen.getByRole('button', { name: /select or create labels/i })
    await user.click(toggle)

    const searchInput = screen.getByPlaceholderText(/select or create labels/i)
    await user.type(searchInput, 'prod')

    await waitFor(
      () => {
        expect(onSearchLabels).toHaveBeenCalledWith('prod')
      },
      { timeout: 500 }
    )
  })

  it('allows selecting job type', async () => {
    const user = userEvent.setup()
    mockTemplateDetail.ask_job_type_on_launch = true

    render(
      <TestWrapper>
        <PromptOnLaunchFields
          extraVarsEditorRef={{ current: null }}
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          executionEnvironments={[]}
          loadingExecutionEnvironments={false}
          credentials={[]}
          loadingCredentials={false}
          instanceGroups={[]}
          loadingInstanceGroups={false}
          onSearchInventories={vi.fn()}
          onSearchExecutionEnvironments={vi.fn()}
          onSearchCredentials={vi.fn()}
          onSearchInstanceGroups={vi.fn()}
          labels={[]}
          loadingLabels={false}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const jobTypeToggle = screen.getByRole('button', { name: 'Run type' })
    await user.click(jobTypeToggle)
    await user.click(screen.getByRole('option', { name: 'Check (Dry Run)' }))

    expect(jobTypeToggle).toHaveTextContent('Check (Dry Run)')
  })
})
