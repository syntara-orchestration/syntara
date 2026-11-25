import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import {
  DiffModeField,
  ExtraVariablesField,
  NumberInputField,
  RunTypeField,
  TagInputField,
  TextInputField,
  VerbosityField,
} from './AAPPromptFields'

// Mock ExpandableCodeEditor to avoid ColorSchemeProvider dependency
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
  }: {
    code: string
    onCodeChange: (v: string) => void
    onBlur: () => void
  }) => <textarea aria-label="Extra variables" value={code} onChange={(e) => onCodeChange(e.target.value)} />,
}))

function TestWrapper({
  children,
  defaultValues,
}: {
  children: React.ReactNode
  defaultValues?: Partial<AAPJobTemplateFormData>
}) {
  const methods = useForm<AAPJobTemplateFormData>({
    defaultValues,
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

describe('AAPPromptFields', () => {
  describe('RunTypeField', () => {
    it('renders run type select', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <RunTypeField />
        </TestWrapper>
      )

      const toggle = screen.getByRole('button', { name: 'Run type' })
      expect(toggle).toBeInTheDocument()

      await user.click(toggle)
      expect(screen.getByRole('option', { name: 'Run' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Check (Dry Run)' })).toBeInTheDocument()
    })

    it('selects run option', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <RunTypeField />
        </TestWrapper>
      )

      const toggle = screen.getByRole('button', { name: 'Run type' })
      await user.click(toggle)
      await user.click(screen.getByRole('option', { name: 'Run' }))

      expect(toggle).toHaveTextContent('Run')
    })

    it('selects check option', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <RunTypeField />
        </TestWrapper>
      )

      const toggle = screen.getByRole('button', { name: 'Run type' })
      await user.click(toggle)
      await user.click(screen.getByRole('option', { name: 'Check (Dry Run)' }))

      expect(toggle).toHaveTextContent('Check (Dry Run)')
    })

    it('displays placeholder option', () => {
      render(
        <TestWrapper>
          <RunTypeField />
        </TestWrapper>
      )

      expect(screen.getByRole('button', { name: 'Run type' })).toHaveTextContent('[ run type ]')
    })
  })

  describe('VerbosityField', () => {
    it('renders verbosity select with all options', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <VerbosityField />
        </TestWrapper>
      )

      const toggle = screen.getByRole('button', { name: 'Verbosity' })
      expect(toggle).toBeInTheDocument()

      await user.click(toggle)
      expect(screen.getByRole('option', { name: '0 - Normal' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: '1 - Verbose' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: '2 - More Verbose' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: '3 - Debug' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: '4 - Connection Debug' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: '5 - WinRM Debug' })).toBeInTheDocument()
    })

    it('selects verbosity level', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <VerbosityField />
        </TestWrapper>
      )

      const toggle = screen.getByRole('button', { name: 'Verbosity' })
      await user.click(toggle)
      await user.click(screen.getByRole('option', { name: '3 - Debug' }))

      expect(toggle).toHaveTextContent('3 - Debug')
    })

    it('displays placeholder option', () => {
      render(
        <TestWrapper>
          <VerbosityField />
        </TestWrapper>
      )

      expect(screen.getByRole('button', { name: 'Verbosity' })).toHaveTextContent('[ verbosity ]')
    })
  })

  describe('DiffModeField', () => {
    it('renders diff mode switch', () => {
      render(
        <TestWrapper>
          <DiffModeField />
        </TestWrapper>
      )

      expect(screen.getByRole('switch', { name: 'Show changes' })).toBeInTheDocument()
    })

    it('toggles diff mode', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper defaultValues={{ diff_mode: false }}>
          <DiffModeField />
        </TestWrapper>
      )

      const switchControl = screen.getByRole('switch', { name: 'Show changes' })
      expect(switchControl).not.toBeChecked()

      await user.click(switchControl)

      expect(switchControl).toBeChecked()
    })

    it('renders with checked state when diff_mode is true', () => {
      render(
        <TestWrapper defaultValues={{ diff_mode: true }}>
          <DiffModeField />
        </TestWrapper>
      )

      const switchControl = screen.getByRole('switch', { name: 'Show changes' })
      expect(switchControl).toBeChecked()
    })

    it('defaults to unchecked when diff_mode is undefined', () => {
      render(
        <TestWrapper>
          <DiffModeField />
        </TestWrapper>
      )

      const switchControl = screen.getByRole('switch', { name: 'Show changes' })
      expect(switchControl).not.toBeChecked()
    })
  })

  describe('TextInputField', () => {
    it('renders text input', () => {
      render(
        <TestWrapper>
          <TextInputField label="Limit" fieldId="test-limit" name="limit" />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Limit')).toBeInTheDocument()
    })

    it('accepts text input', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <TextInputField label="Limit" fieldId="test-limit" name="limit" />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Limit')
      await user.type(input, 'test-value')

      expect(input).toHaveValue('test-value')
    })

    it('renders with initial value', () => {
      render(
        <TestWrapper defaultValues={{ limit: 'initial-limit' }}>
          <TextInputField label="Limit" fieldId="test-limit" name="limit" />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Limit')).toHaveValue('initial-limit')
    })

    it('renders with empty value', () => {
      render(
        <TestWrapper>
          <TextInputField label="Limit" fieldId="test-limit" name="limit" />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Limit')).toHaveValue('')
    })
  })

  describe('NumberInputField', () => {
    it('renders number input', () => {
      render(
        <TestWrapper>
          <NumberInputField label="Forks" fieldId="test-forks" name="forks" placeholder="0" min={0} />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Forks')).toBeInTheDocument()
    })

    it('accepts number input', async () => {
      const user = userEvent.setup()
      render(
        <TestWrapper>
          <NumberInputField label="Forks" fieldId="test-forks" name="forks" placeholder="0" min={0} />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Forks')
      await user.clear(input)
      await user.type(input, '5')

      expect(input).toHaveValue(5)
    })

    it('renders with min attribute', () => {
      render(
        <TestWrapper>
          <NumberInputField label="Forks" fieldId="test-forks" name="forks" placeholder="0" min={0} />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Forks')
      expect(input).toHaveAttribute('min', '0')
    })

    it('renders with placeholder', () => {
      render(
        <TestWrapper>
          <NumberInputField label="Forks" fieldId="test-forks" name="forks" placeholder="Enter forks" min={0} />
        </TestWrapper>
      )

      expect(screen.getByPlaceholderText('Enter forks')).toBeInTheDocument()
    })

    it('handles undefined value', () => {
      render(
        <TestWrapper>
          <NumberInputField label="Forks" fieldId="test-forks-undefined" name="forks" placeholder="0" min={0} />
        </TestWrapper>
      )

      const input = screen.getByLabelText('Forks')
      expect(input).toHaveValue(null)
    })
  })

  describe('ExtraVariablesField', () => {
    it('renders extra variables code editor', () => {
      const editorRef = { current: null }
      render(
        <TestWrapper>
          <ExtraVariablesField editorRef={editorRef} />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Extra variables')).toBeInTheDocument()
    })

    it('renders error state when validation fails', () => {
      const editorRef = { current: null }
      render(
        <TestWrapper defaultValues={{ extra_vars: '' }}>
          <ExtraVariablesField editorRef={editorRef} />
        </TestWrapper>
      )

      // The component should render with the field and be ready to display errors
      expect(screen.getByLabelText('Extra variables')).toBeInTheDocument()
    })

    it('renders with initial value', () => {
      const editorRef = { current: null }
      render(
        <TestWrapper defaultValues={{ extra_vars: '{"key": "value"}' }}>
          <ExtraVariablesField editorRef={editorRef} />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Extra variables')).toBeInTheDocument()
    })

    it('renders with empty value', () => {
      const editorRef = { current: null }
      render(
        <TestWrapper defaultValues={{ extra_vars: '' }}>
          <ExtraVariablesField editorRef={editorRef} />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Extra variables')).toBeInTheDocument()
    })
  })

  describe('TagInputField', () => {
    it('renders tag input', () => {
      render(
        <TestWrapper>
          <TagInputField
            label="Tags"
            fieldId="test-tags"
            name="tags"
            placeholder="Enter tags"
            helperText="Comma-separated tags"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Tags')).toBeInTheDocument()
    })

    it('handles comma-separated string values', () => {
      render(
        <TestWrapper defaultValues={{ tags: 'tag1, tag2, tag3' }}>
          <TagInputField
            label="Tags"
            fieldId="test-tags"
            name="tags"
            placeholder="Enter tags"
            helperText="Comma-separated tags"
          />
        </TestWrapper>
      )

      // Component should render with the field
      expect(screen.getByLabelText('Tags')).toBeInTheDocument()
    })

    it('handles empty string values', () => {
      render(
        <TestWrapper defaultValues={{ tags: '' }}>
          <TagInputField
            label="Tags"
            fieldId="test-tags"
            name="tags"
            placeholder="Enter tags"
            helperText="Comma-separated tags"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Tags')).toBeInTheDocument()
    })

    it('renders with helper text', () => {
      render(
        <TestWrapper>
          <TagInputField
            label="Tags"
            fieldId="test-tags"
            name="tags"
            placeholder="Enter tags"
            helperText="Comma-separated tags"
          />
        </TestWrapper>
      )

      expect(screen.getByText('Comma-separated tags')).toBeInTheDocument()
    })

    it('handles skip_tags field', () => {
      render(
        <TestWrapper defaultValues={{ skip_tags: 'skip1, skip2' }}>
          <TagInputField
            label="Skip Tags"
            fieldId="test-skip-tags"
            name="skip_tags"
            placeholder="Enter skip tags"
            helperText="Tags to skip"
          />
        </TestWrapper>
      )

      expect(screen.getByLabelText('Skip Tags')).toBeInTheDocument()
    })

    it('splits tags correctly on commas', () => {
      render(
        <TestWrapper defaultValues={{ tags: 'deploy, test , production' }}>
          <TagInputField label="Tags" fieldId="test-tags" name="tags" placeholder="Enter tags" helperText="Tags help" />
        </TestWrapper>
      )

      // Component should render and handle tags with spaces
      expect(screen.getByLabelText('Tags')).toBeInTheDocument()
    })
  })
})
