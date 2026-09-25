import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldTypeEnum, parseFormDefinition } from '../../forms'

import { invalidDynamicFormDefinition, sampleDynamicFormDefinition } from './dynamicForm/synDynamicFormFixtures'
import { SynDynamicForm } from './SynDynamicForm'

const staticPriorityOptions = {
  source: 'static' as const,
  values: [
    { display_label: 'Low', value: 'low' },
    { display_label: 'High', value: 'high' },
  ],
}

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('SynDynamicForm', () => {
  it('renders fields from the definition', () => {
    renderWithQueryClient(
      <SynDynamicForm definition={sampleDynamicFormDefinition} onSubmit={vi.fn()} hideSubmitButton />
    )

    expect(screen.getByRole('textbox', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Email' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Subscribe to updates' })).toBeInTheDocument()
  })

  it('shows SynErrorState for invalid definition defaults', () => {
    renderWithQueryClient(<SynDynamicForm definition={invalidDynamicFormDefinition} onSubmit={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Invalid form configuration' })).toBeInTheDocument()
  })

  it('submits coerced values when valid', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    const minimal = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name', required: true },
        { type: FormFieldTypeEnum.CHECKBOX, value_name: 'agree', label: 'Agree', required: true },
      ],
    })

    renderWithQueryClient(<SynDynamicForm definition={minimal} onSubmit={onSubmit} submitLabel="Send" />)

    await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Ada')
    await user.click(screen.getByRole('checkbox', { name: 'Agree' }))
    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({ name: 'Ada', agree: true })
    })
  })

  it('shows field errors when submission is invalid', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const onValidationError = vi.fn()

    const minimal = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name', required: true }],
    })

    renderWithQueryClient(
      <SynDynamicForm
        definition={minimal}
        onSubmit={onSubmit}
        onValidationError={onValidationError}
        submitLabel="Send"
      />
    )

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled()
      expect(onValidationError).toHaveBeenCalled()
      expect(screen.getByText('This field is required')).toBeInTheDocument()
    })
  })

  it('submits number, date, textarea, and static select fields', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    const definition = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.NUMBER, value_name: 'count', label: 'Count', default: 3, required: true },
        { type: FormFieldTypeEnum.DATE, value_name: 'start', label: 'Start', default: '2026-02-01', required: true },
        { type: FormFieldTypeEnum.TEXTAREA, value_name: 'notes', label: 'Notes', required: true },
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'priority',
          label: 'Priority',
          required: true,
          options: staticPriorityOptions,
        },
      ],
    })

    renderWithQueryClient(<SynDynamicForm definition={definition} onSubmit={onSubmit} submitLabel="Send" />)

    await user.type(screen.getByRole('textbox', { name: 'Notes' }), 'hello')

    await user.click(screen.getByRole('button', { name: 'Priority' }))
    await user.click(await screen.findByRole('option', { name: 'High' }))

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        count: 3,
        start: '2026-02-01',
        notes: 'hello',
        priority: 'high',
      })
    })
  })

  it('submits multi-select values from initialValues', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.MULTI_SELECT,
          value_name: 'tags',
          label: 'Tags',
          required: true,
          options: staticPriorityOptions,
        },
      ],
    })

    renderWithQueryClient(
      <SynDynamicForm
        definition={definition}
        initialValues={{ tags: ['low', 'high'] }}
        onSubmit={onSubmit}
        submitLabel="Send"
      />
    )

    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({ tags: ['low', 'high'] })
    })
  })

  it('loads dynamic options via TanStack Query', async () => {
    const user = userEvent.setup()
    const resolveDynamicOptions = vi.fn().mockResolvedValue([
      { label: 'US East', value: 'use1' },
      { label: 'EU West', value: 'euw1' },
    ])

    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'region',
          label: 'Region',
          options: { source: 'dynamic', expression: '${nodes.x}' },
        },
      ],
    })

    renderWithQueryClient(
      <SynDynamicForm
        definition={definition}
        onSubmit={vi.fn()}
        resolveDynamicOptions={resolveDynamicOptions}
        hideSubmitButton
      />
    )

    await waitFor(() => {
      expect(resolveDynamicOptions).toHaveBeenCalled()
    })

    await user.click(screen.getByRole('button', { name: 'Region' }))
    expect(await screen.findByRole('option', { name: 'US East' })).toBeInTheDocument()
  })

  it('maps dynamic option records using label_key and value_key', async () => {
    const user = userEvent.setup()
    const resolveDynamicOptions = vi.fn().mockResolvedValue([{ name: 'US East', id: 'use1' }])

    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'region',
          label: 'Region',
          options: {
            source: 'dynamic',
            expression: '${nodes.upstream.regions}',
            label_key: 'name',
            value_key: 'id',
          },
        },
      ],
    })

    renderWithQueryClient(
      <SynDynamicForm
        definition={definition}
        onSubmit={vi.fn()}
        resolveDynamicOptions={resolveDynamicOptions}
        hideSubmitButton
      />
    )

    await user.click(screen.getByRole('button', { name: 'Region' }))
    expect(await screen.findByRole('option', { name: 'US East' })).toBeInTheDocument()
  })

  it('has no accessibility violations on initial render', async () => {
    const { container } = renderWithQueryClient(
      <SynDynamicForm
        definition={sampleDynamicFormDefinition}
        description="Please complete the form."
        onSubmit={vi.fn()}
        submitLabel="Submit form"
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when validation errors are shown', async () => {
    const user = userEvent.setup()
    const { container } = renderWithQueryClient(
      <SynDynamicForm
        definition={parseFormDefinition({
          fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name', required: true }],
        })}
        onSubmit={vi.fn()}
        submitLabel="Submit form"
      />
    )

    await user.click(screen.getByRole('button', { name: 'Submit form' }))
    await screen.findByText('This field is required')

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
