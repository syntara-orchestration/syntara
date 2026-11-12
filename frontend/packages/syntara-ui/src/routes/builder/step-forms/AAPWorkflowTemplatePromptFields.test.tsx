import { render, screen } from '@testing-library/react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { AAPWorkflowTemplateDetail } from '../../../hooks/useAAPBrowser'

import { AAPWorkflowTemplatePromptFields } from './AAPWorkflowTemplatePromptFields'
import type { AAPWorkflowTemplateFormData } from './aapWorkflowTemplateSchema'

function TestWrapper({ children }: { children: React.ReactNode }) {
  const methods = useForm<AAPWorkflowTemplateFormData>({
    defaultValues: {
      name: 'Test Workflow',
      organization_name: 'Default',
      workflow_job_template_name: 'Deploy Workflow',
      workflow_job_template_id: 20,
    },
  })

  return <FormProvider {...methods}>{children}</FormProvider>
}

const mockTemplateDetail: AAPWorkflowTemplateDetail = {
  id: 20,
  name: 'Deploy Workflow',
  description: 'Test workflow',
  ask_inventory_on_launch: true,
  ask_variables_on_launch: true,
  ask_limit_on_launch: true,
  ask_scm_branch_on_launch: true,
  ask_labels_on_launch: true,
  ask_tags_on_launch: true,
  ask_skip_tags_on_launch: true,
  survey_enabled: false,
  url: 'https://aap.example.com/templates/20',
  default_inventory: { id: 1, name: 'Demo Inventory' },
  default_labels: [],
}

const mockInventories = [
  { id: 1, name: 'Demo Inventory' },
  { id: 2, name: 'Production Inventory' },
]

const mockLabels = [
  { id: 1, name: 'production' },
  { id: 2, name: 'staging' },
]

describe('AAPWorkflowTemplatePromptFields', () => {
  it('renders nothing when templateDetail is null and not loading', () => {
    const { container } = render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={undefined}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          labels={[]}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when template has no prompt-on-launch fields', () => {
    const templateWithNoPrompts: AAPWorkflowTemplateDetail = {
      ...mockTemplateDetail,
      ask_inventory_on_launch: false,
      ask_variables_on_launch: false,
      ask_limit_on_launch: false,
      ask_scm_branch_on_launch: false,
      ask_labels_on_launch: false,
      ask_tags_on_launch: false,
      ask_skip_tags_on_launch: false,
    }

    const { container } = render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={templateWithNoPrompts}
          isLoadingDetail={false}
          inventories={[]}
          loadingInventories={false}
          labels={[]}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('renders prompt on launch section when fields are enabled', () => {
    render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          labels={mockLabels}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByText('Prompt on launch')).toBeInTheDocument()
  })

  it('renders inventory field when ask_inventory_on_launch is true', () => {
    render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          labels={mockLabels}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByText('Inventory')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Demo Inventory \(default\)/i)).toBeInTheDocument()
  })

  it('renders all prompt-on-launch fields when enabled', () => {
    render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          labels={mockLabels}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByText('Inventory')).toBeInTheDocument()
    expect(screen.getByText('Job tags')).toBeInTheDocument()
    expect(screen.getByText('Limit')).toBeInTheDocument()
    expect(screen.getByText('Labels')).toBeInTheDocument()
    expect(screen.getByText('Skip tags')).toBeInTheDocument()
  })

  it('attaches field help popovers to prompt-on-launch labels', () => {
    render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          labels={mockLabels}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    for (const label of ['Inventory', 'Labels', 'Limit', 'Source control branch', 'Job tags', 'Skip tags']) {
      expect(screen.getByRole('button', { name: `More info for ${label}` })).toBeInTheDocument()
    }
  })

  it('shows default inventory name in placeholder', () => {
    render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          labels={mockLabels}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByPlaceholderText(/Demo Inventory \(default\)/i)).toBeInTheDocument()
  })

  it('shows "No default inventory" when no default is set', () => {
    const templateWithoutDefaultInventory: AAPWorkflowTemplateDetail = {
      ...mockTemplateDetail,
      default_inventory: null,
    }

    render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={templateWithoutDefaultInventory}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          labels={mockLabels}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    expect(screen.getByPlaceholderText(/No default inventory/i)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <TestWrapper>
        <AAPWorkflowTemplatePromptFields
          templateDetail={mockTemplateDetail}
          isLoadingDetail={false}
          inventories={mockInventories}
          loadingInventories={false}
          labels={mockLabels}
          loadingLabels={false}
          onSearchInventories={vi.fn()}
          onSearchLabels={vi.fn()}
        />
      </TestWrapper>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
