import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import { ExpressionTextField } from './ExpressionTextField'

// Test wrapper that provides react-hook-form context
function TestWrapper({
  children,
  defaultValues = {},
}: {
  children: React.ReactNode
  defaultValues?: Partial<AAPJobTemplateFormData>
}) {
  const methods = useForm<AAPJobTemplateFormData>({
    defaultValues: {
      name: '',
      organization_name: '',
      job_template_name: '',
      ...defaultValues,
    },
  })

  return <FormProvider {...methods}>{children}</FormProvider>
}

describe('ExpressionTextField', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders the field with label and placeholder', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Organization')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Enter organization name')).toBeInTheDocument()
    })

    it('renders with required indicator when isRequired is true', () => {
      const { container } = render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
            isRequired
          />
        </TestWrapper>
      )

      // PatternFly adds asterisk for required fields
      // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- PatternFly required indicator is not accessible via accessible queries
      const requiredIndicator = container.querySelector('.pf-v6-c-form__label-required')
      expect(requiredIndicator).toBeInTheDocument()
    })

    it('renders without required indicator when isRequired is false', () => {
      const { container } = render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
            isRequired={false}
          />
        </TestWrapper>
      )

      // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- PatternFly required indicator is not accessible via accessible queries
      const requiredIndicator = container.querySelector('.pf-v6-c-form__label-required')
      expect(requiredIndicator).not.toBeInTheDocument()
    })

    it('displays helper text about drag and drop', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      expect(screen.getByText('Enter a value or drag an expression from the Input panel')).toBeInTheDocument()
    })

    it('does not show syntax validation for plain text values', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Organization')
      await user.type(input, 'Default')

      expect(screen.queryByText('Invalid syntax')).not.toBeInTheDocument()
    })
  })

  describe('User Input', () => {
    it('allows typing text into the field', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Organization')
      await user.type(input, 'my-org')

      expect(input).toHaveValue('my-org')
    })

    it('clears text when user clears the field', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper defaultValues={{ organization_name: 'initial-value' }}>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Organization')
      expect(input).toHaveValue('initial-value')

      await user.clear(input)
      expect(input).toHaveValue('')
    })

    it('allows typing expression syntax', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Organization')
      // Use paste to avoid userEvent's special handling of braces
      await user.click(input)
      await user.paste('${outputs.step1.organization}')

      expect(input).toHaveValue('${outputs.step1.organization}')
    })
  })

  describe('Initial Values', () => {
    it('displays initial value from form context', () => {
      render(
        <TestWrapper defaultValues={{ organization_name: 'Default Org' }}>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Organization')).toHaveValue('Default Org')
    })

    it('renders empty field when no initial value provided', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Organization')).toHaveValue('')
    })
  })

  describe('Different Field Types', () => {
    it('renders for job_template_name field', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="job_template_name"
            id="job-template-field"
            label="Job Template"
            placeholder="Enter job template"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Job Template')).toBeInTheDocument()
    })

    it('renders for inventory_name field', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="inventory_name"
            id="inventory-field"
            label="Inventory"
            placeholder="Enter inventory"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Inventory')).toBeInTheDocument()
    })

    it('renders for limit field', () => {
      render(
        <TestWrapper>
          <ExpressionTextField name="limit" id="limit-field" label="Limit" placeholder="Enter host pattern" />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Limit')).toBeInTheDocument()
    })

    it('renders for extra_vars field', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="extra_vars"
            id="extra-vars-field"
            label="Extra Variables"
            placeholder="Enter extra variables"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Extra Variables')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
            isRequired
          />
        </TestWrapper>
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('associates label with input via fieldId', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="org-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Organization')
      expect(input).toHaveAttribute('id', 'org-field')
    })

    it('has accessible helper text', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      const helperText = screen.getByText('Enter a value or drag an expression from the Input panel')
      expect(helperText).toBeInTheDocument()
      // Helper text is rendered within PatternFly's FormHelperText component
      expect(helperText).toBeVisible()
    })
  })

  describe('Component Structure', () => {
    it('renders with droppable field wrapper', () => {
      const { container } = render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      // The component should render a FormGroup
      // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- PatternFly internal structure verification
      expect(container.querySelector('.pf-v6-c-form__group')).toBeInTheDocument()
      // The component should render an input
      expect(screen.getByLabelText('Organization')).toBeInTheDocument()
      // The component should render helper text
      expect(screen.getByText('Enter a value or drag an expression from the Input panel')).toBeInTheDocument()
    })
  })

  describe('Integration with react-hook-form', () => {
    it('registers field with react-hook-form', async () => {
      const user = userEvent.setup()
      const handleSubmit = vi.fn()

      function FormWithSubmit() {
        const methods = useForm<AAPJobTemplateFormData>({
          defaultValues: {
            name: '',
            organization_name: '',
            job_template_name: '',
          },
        })

        return (
          <FormProvider {...methods}>
            <form onSubmit={methods.handleSubmit(handleSubmit)}>
              <ExpressionTextField
                name="organization_name"
                id="test-field"
                label="Organization"
                placeholder="Enter organization name"
              />
              <button type="submit">Submit</button>
            </form>
          </FormProvider>
        )
      }

      render(<FormWithSubmit />)

      const input = screen.getByLabelText('Organization')
      await user.type(input, 'test-org')

      const submitButton = screen.getByRole('button', { name: 'Submit' })
      await user.click(submitButton)

      expect(handleSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          organization_name: 'test-org',
        }),
        expect.anything()
      )
    })
  })

  describe('Drag and Drop', () => {
    it('wraps input in DroppableField component', () => {
      const { container } = render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      // The DroppableField wrapper should exist (contains the input)
      const input = screen.getByLabelText('Organization')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'text')

      // FormGroup structure should be present
      // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- PatternFly internal structure verification
      expect(container.querySelector('.pf-v6-c-form__group')).toBeInTheDocument()
    })

    it('renders helper text about drag and drop support', () => {
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      // Helper text should indicate drag and drop is supported
      expect(screen.getByText('Enter a value or drag an expression from the Input panel')).toBeInTheDocument()
    })

    it('accepts manual text input for expressions', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <ExpressionTextField
            name="organization_name"
            id="test-field"
            label="Organization"
            placeholder="Enter organization name"
          />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Organization')
      await user.click(input)
      await user.paste('${outputs.step1.organization}')

      expect(input).toHaveValue('${outputs.step1.organization}')
    })
  })
})
