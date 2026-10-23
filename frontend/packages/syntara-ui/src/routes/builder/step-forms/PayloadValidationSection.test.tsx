import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { PayloadValidationSection } from './PayloadValidationSection'
import { DEFAULT_JSON_SCHEMA, EXAMPLE_JSON_SCHEMA, JSON_SCHEMA_DOWNLOAD_FILENAME } from './triggerFormSchema'

vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (val: string) => void
    ariaLabel: string
    onBlur?: () => void
    language?: string
    height?: string
    modalTitle?: string
    additionalControls?: ReactNode
  }) => <textarea aria-label={ariaLabel} value={code} onChange={(e) => onCodeChange(e.target.value)} />,
}))

vi.mock('../components/JsonEditorToolbar', () => ({
  JsonEditorControls: () => null,
}))

function Wrapper({ children, initialSchema = '' }: Readonly<{ children: ReactNode; initialSchema?: string }>) {
  const methods = useForm({ defaultValues: { inputSchema: initialSchema, triggerType: 'webhook_trigger' } })
  return <FormProvider {...methods}>{children}</FormProvider>
}

const defaultProps = {
  defaultCode: DEFAULT_JSON_SCHEMA,
  exampleCode: EXAMPLE_JSON_SCHEMA,
  modalTitle: 'Edit JSON schema',
  ariaLabel: 'JSON schema validation editor',
  downloadFilename: JSON_SCHEMA_DOWNLOAD_FILENAME,
  helperText: 'Optional helper text.',
}

describe('PayloadValidationSection', () => {
  it('renders Simple mode by default with Add field button', () => {
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    expect(screen.getByRole('button', { name: 'Simple' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Add field' })).toBeInTheDocument()
  })

  it('switches to Advanced mode and shows the code editor', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))

    expect(screen.getByRole('textbox', { name: 'JSON schema validation editor' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add field' })).not.toBeInTheDocument()
  })

  it('shows helper text only in Advanced mode', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    expect(screen.queryByText('Optional helper text.')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    expect(screen.getByText('Optional helper text.')).toBeInTheDocument()
  })

  it('switches back to Simple mode from Advanced', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    await user.click(screen.getByRole('button', { name: 'Simple' }))

    expect(screen.getByRole('button', { name: 'Add field' })).toBeInTheDocument()
  })

  it('shows validation error when switching to Simple with a complex schema', async () => {
    const user = userEvent.setup()
    const complexSchema = JSON.stringify({
      type: 'object',
      oneOf: [{ properties: { a: { type: 'string' } } }],
    })

    render(
      <Wrapper initialSchema={complexSchema}>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    await user.click(screen.getByRole('button', { name: 'Simple' }))

    expect(screen.getByText(/not supported in simple mode/)).toBeInTheDocument()
  })

  it('shows validation error when switching to Simple with invalid JSON', async () => {
    const user = userEvent.setup()

    render(
      <Wrapper initialSchema="not valid json">
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    await user.click(screen.getByRole('button', { name: 'Simple' }))

    expect(screen.getByText(/Invalid JSON syntax/)).toBeInTheDocument()
  })

  it('clears switch error when switching back to Advanced', async () => {
    const user = userEvent.setup()

    render(
      <Wrapper initialSchema="not valid json">
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    await user.click(screen.getByRole('button', { name: 'Simple' }))
    expect(screen.getByText(/Invalid JSON syntax/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    expect(screen.queryByText(/Invalid JSON syntax/)).not.toBeInTheDocument()
  })

  it('shows error text when error prop is provided', () => {
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} error="Invalid JSON syntax" />
      </Wrapper>
    )

    expect(screen.getByText('Invalid JSON syntax')).toBeInTheDocument()
  })

  it('renders a label when provided', () => {
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} label="Request body" />
      </Wrapper>
    )

    expect(screen.getByText('Request body')).toBeInTheDocument()
  })

  it('hides helper text in Advanced mode when error is present', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} error="Bad JSON" />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))

    expect(screen.getByText('Bad JSON')).toBeInTheDocument()
    expect(screen.queryByText('Optional helper text.')).not.toBeInTheDocument()
  })

  it('adds a field in Simple mode via the Add field button', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Add field' }))

    expect(screen.getByRole('textbox', { name: 'Field name 1' })).toBeInTheDocument()
  })

  it('stays in Advanced mode when schema cannot be simplified', async () => {
    const user = userEvent.setup()
    const complexSchema = JSON.stringify({
      type: 'object',
      oneOf: [{ properties: { a: { type: 'string' } } }],
    })

    render(
      <Wrapper initialSchema={complexSchema}>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    await user.click(screen.getByRole('button', { name: 'Simple' }))

    expect(screen.getByRole('textbox', { name: 'JSON schema validation editor' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add field' })).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('shows switch error as validation error below the editor', async () => {
    const user = userEvent.setup()
    const complexSchema = JSON.stringify({
      type: 'object',
      oneOf: [{ properties: { a: { type: 'string' } } }],
    })

    render(
      <Wrapper initialSchema={complexSchema}>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    await user.click(screen.getByRole('button', { name: 'Simple' }))

    expect(screen.getByText(/not supported in simple mode/)).toBeInTheDocument()
    expect(screen.queryByText('Optional helper text.')).not.toBeInTheDocument()
  })

  it('defaults to Advanced mode when initial schema is complex', () => {
    const complexSchema = JSON.stringify({
      type: 'object',
      properties: { data: { type: 'object', properties: { nested: { type: 'string' } } } },
    })

    render(
      <Wrapper initialSchema={complexSchema}>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    expect(screen.getByRole('button', { name: 'Advanced' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('textbox', { name: 'JSON schema validation editor' })).toBeInTheDocument()
  })

  it('does not show default code placeholder in Advanced editor when schema is empty', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper initialSchema="">
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))

    const editor = screen.getByRole('textbox', { name: 'JSON schema validation editor' })
    expect(editor).toHaveValue('')
  })

  it('handles empty inputSchema value', () => {
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    expect(screen.getByRole('button', { name: 'Add field' })).toBeInTheDocument()
  })

  it('parses initial schema fields when mounting in Simple mode', () => {
    const schema = JSON.stringify({
      type: 'object',
      properties: { event: { type: 'string' } },
      additionalProperties: true,
    })

    render(
      <Wrapper initialSchema={schema}>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    expect(screen.getByDisplayValue('event')).toBeInTheDocument()
  })

  it('renders with no label and no error in Simple mode', () => {
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    expect(screen.getByRole('button', { name: 'Simple' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByText('Optional helper text.')).not.toBeInTheDocument()
  })

  it('renders Advanced mode with helper text and no error', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    expect(screen.getByText('Optional helper text.')).toBeInTheDocument()
  })

  it('renders with both label and error', () => {
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} label="Request body" error="Schema is invalid" />
      </Wrapper>
    )

    expect(screen.getByText('Request body')).toBeInTheDocument()
    expect(screen.getByText('Schema is invalid')).toBeInTheDocument()
  })

  it('shows form error over switch error when both exist', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper initialSchema="bad json">
        <PayloadValidationSection {...defaultProps} error="Form validation error" />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    await user.click(screen.getByRole('button', { name: 'Simple' }))

    expect(screen.getByText('Form validation error')).toBeInTheDocument()
  })

  it('shows switch error when no form error exists', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper initialSchema="bad json">
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    await user.click(screen.getByRole('button', { name: 'Simple' }))

    expect(screen.getByText(/Invalid JSON syntax/)).toBeInTheDocument()
  })

  it('renders with empty string initial schema in Advanced mode', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper initialSchema="">
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    expect(screen.getByRole('textbox', { name: 'JSON schema validation editor' })).toBeInTheDocument()
  })

  it('switches from Simple to Advanced and back preserving mode', async () => {
    const user = userEvent.setup()
    render(
      <Wrapper>
        <PayloadValidationSection {...defaultProps} />
      </Wrapper>
    )

    await user.click(screen.getByRole('button', { name: 'Advanced' }))
    expect(screen.getByRole('button', { name: 'Advanced' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(screen.getByRole('button', { name: 'Simple' }))
    expect(screen.getByRole('button', { name: 'Simple' })).toHaveAttribute('aria-pressed', 'true')
  })
})
