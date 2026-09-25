import type { FormDefinition } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldTypeEnum, formDefinitionToJsonSchemaString, parseFormDefinition } from '../../forms'

import { createEmptyFormDefinition } from './formFieldBuilder/createDefaultField'
import { SynFormFieldBuilder } from './SynFormFieldBuilder'

function renderBuilder(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

function dropdownFieldDefinition() {
  return parseFormDefinition({
    fields: [
      {
        type: FormFieldTypeEnum.DROPDOWN,
        value_name: 'choice',
        label: 'Choice',
        options: {
          source: 'static',
          values: [
            { display_label: 'Alpha', value: 'alpha' },
            { display_label: 'Beta', value: 'beta' },
          ],
        },
      },
    ],
  })
}

function multiSelectFieldDefinition() {
  return parseFormDefinition({
    fields: [
      {
        type: FormFieldTypeEnum.MULTI_SELECT,
        value_name: 'tags',
        label: 'Tags',
        options: {
          source: 'static',
          values: [
            { display_label: 'One', value: 'one' },
            { display_label: 'Two', value: 'two' },
          ],
        },
      },
    ],
  })
}

describe('SynFormFieldBuilder', () => {
  it('renders design tab and adds a field', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const initial = createEmptyFormDefinition()

    renderBuilder(<SynFormFieldBuilder value={initial} onChange={onChange} />)

    expect(screen.getByRole('tab', { name: 'Design' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Preview' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add field' }))

    const labelInputs = screen.getAllByRole('textbox', { name: 'Field label' })
    expect(labelInputs).toHaveLength(2)
    await user.type(labelInputs[0], 'First')
    await user.type(labelInputs[1], 'Second')
    expect(onChange).toHaveBeenCalled()
    const lastCall = onChange.mock.calls.at(-1)?.[0] as FormDefinition
    expect(lastCall.fields).toHaveLength(2)
    expect(lastCall.fields[1]?.label).toBe('Second')
  })

  it('shows preview when definition is valid', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'title', label: 'Title', required: true }],
    })

    renderBuilder(<SynFormFieldBuilder value={definition} onChange={vi.fn()} />)

    await user.click(screen.getByRole('tab', { name: 'Preview' }))
    const previewPanel = screen.getAllByRole('tabpanel').find((panel) => !panel.hasAttribute('hidden'))
    if (!previewPanel) {
      throw new Error('Expected visible preview tab panel')
    }
    expect(within(previewPanel).getByRole('textbox', { name: 'Title' })).toBeInTheDocument()
  })

  it('removes a field after confirmation', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const initial = createEmptyFormDefinition()

    renderBuilder(<SynFormFieldBuilder value={initial} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: 'Add field' }))
    const labelInputs = screen.getAllByRole('textbox', { name: 'Field label' })
    await user.type(labelInputs[1], 'Extra')

    await user.click(screen.getByRole('button', { name: 'Remove field 2' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: /Remove field\?/ })).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Remove field' }))
    await waitFor(() => {
      expect(screen.getAllByRole('textbox', { name: 'Field label' })).toHaveLength(1)
    })
  })

  it('has no accessibility violations on design tab', async () => {
    const { container } = renderBuilder(<SynFormFieldBuilder value={createEmptyFormDefinition()} onChange={vi.fn()} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('does not show remove field control when only one field exists', () => {
    renderBuilder(<SynFormFieldBuilder value={createEmptyFormDefinition()} onChange={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Remove field 1' })).not.toBeInTheDocument()
  })

  it('does not show remove option control when dropdown has a single static option', () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'choice',
          label: 'Choice',
          options: {
            source: 'static',
            values: [{ display_label: 'Only', value: 'only' }],
          },
        },
      ],
    })

    renderBuilder(<SynFormFieldBuilder value={definition} onChange={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Remove option 1' })).not.toBeInTheDocument()
  })

  it('loads pasted JSON Schema into the builder', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const definition = parseFormDefinition({
      fields: [
        { type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name', required: true },
        { type: FormFieldTypeEnum.NUMBER, value_name: 'count', label: 'Count' },
      ],
    })
    const schemaJson = formDefinitionToJsonSchemaString(definition)

    renderBuilder(<SynFormFieldBuilder value={createEmptyFormDefinition()} onChange={onChange} />)
    await user.click(screen.getByRole('tab', { name: 'JSON Schema' }))

    await user.clear(screen.getByRole('textbox', { name: 'Import JSON Schema' }))
    await user.paste(schemaJson)
    await user.click(screen.getByRole('button', { name: 'Load into builder' }))
    const replaceDialog = screen.getByRole('dialog')
    await user.click(within(replaceDialog).getByRole('button', { name: 'Replace fields' }))

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled()
    })
    const last = onChange.mock.calls.at(-1)?.[0] as FormDefinition
    expect(last.fields).toHaveLength(2)
    expect(last.fields.map((field) => field.value_name)).toEqual(['name', 'count'])
  })

  it('shows exported JSON Schema when the definition is valid', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'title', label: 'Title', required: true }],
    })

    renderBuilder(<SynFormFieldBuilder value={definition} onChange={vi.fn()} />)
    await user.click(screen.getByRole('tab', { name: 'JSON Schema' }))

    expect(screen.getByLabelText('Generated JSON Schema')).toHaveTextContent('"title"')
    expect(screen.getByLabelText('Generated JSON Schema')).toHaveTextContent('"required"')
  })

  it('changes field type from the design tab', async () => {
    const user = userEvent.setup()
    renderBuilder(<SynFormFieldBuilder value={createEmptyFormDefinition()} onChange={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Text' }))
    await user.click(screen.getByRole('option', { name: 'Number' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Number' })).toBeInTheDocument()
    })
  })

  it('toggles required on a field', async () => {
    const user = userEvent.setup()
    renderBuilder(<SynFormFieldBuilder value={createEmptyFormDefinition()} onChange={vi.fn()} />)

    const required = screen.getByRole('checkbox', { name: 'Required' })
    expect(required).not.toBeChecked()
    await user.click(required)
    expect(required).toBeChecked()
  })

  it('adds a second static option and shows remove control', async () => {
    const user = userEvent.setup()
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'choice',
          label: 'Choice',
          options: {
            source: 'static',
            values: [{ display_label: 'Only', value: 'only' }],
          },
        },
      ],
    })

    renderBuilder(<SynFormFieldBuilder value={definition} onChange={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Add option' }))

    expect(screen.getByRole('button', { name: 'Remove option 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove option 2' })).toBeInTheDocument()
  })

  describe('field defaults and options', () => {
    it('renders date default picker for date fields', async () => {
      const user = userEvent.setup()
      const definition = parseFormDefinition({
        fields: [{ type: FormFieldTypeEnum.DATE, value_name: 'due', label: 'Due', default: null }],
      })
      renderBuilder(<SynFormFieldBuilder value={definition} onChange={vi.fn()} />)
      const dateInput = screen.getByRole('textbox', { name: 'Default date' })
      await user.type(dateInput, '2026-03-15')
      expect(dateInput).toHaveValue('2026-03-15')
    })

    it('renders checkbox default toggle', async () => {
      const user = userEvent.setup()
      const definition = parseFormDefinition({
        fields: [{ type: FormFieldTypeEnum.CHECKBOX, value_name: 'agree', label: 'Agree', default: false }],
      })
      renderBuilder(<SynFormFieldBuilder value={definition} onChange={vi.fn()} />)
      const defaultChecked = screen.getByRole('checkbox', { name: /Default to checked/ })
      expect(defaultChecked).not.toBeChecked()
      await user.click(defaultChecked)
      expect(defaultChecked).toBeChecked()
    })

    it('accepts number default input', async () => {
      const user = userEvent.setup()
      const definition = parseFormDefinition({
        fields: [{ type: FormFieldTypeEnum.NUMBER, value_name: 'qty', label: 'Qty', default: null }],
      })
      renderBuilder(<SynFormFieldBuilder value={definition} onChange={vi.fn()} />)
      const defaultInput = screen.getByRole('spinbutton', { name: 'Default value' })
      await user.type(defaultInput, '12.5')
      expect(defaultInput).toHaveValue(12.5)
    })

    it('accepts text default value', async () => {
      const user = userEvent.setup()
      renderBuilder(<SynFormFieldBuilder value={createEmptyFormDefinition()} onChange={vi.fn()} />)
      const defaultInput = screen.getByRole('textbox', { name: 'Default value' })
      await user.type(defaultInput, 'preset')
      expect(defaultInput).toHaveValue('preset')
    })

    it('selects a dropdown default from static options', async () => {
      const user = userEvent.setup()
      renderBuilder(<SynFormFieldBuilder value={dropdownFieldDefinition()} onChange={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: 'Default value' }))
      await user.click(screen.getByRole('option', { name: 'Beta' }))
      expect(screen.getByRole('button', { name: 'Default value' })).toHaveTextContent('Beta')
    })

    it('toggles multi-select default checkboxes', async () => {
      const user = userEvent.setup()
      renderBuilder(<SynFormFieldBuilder value={multiSelectFieldDefinition()} onChange={vi.fn()} />)

      const one = screen.getByRole('checkbox', { name: 'One' })
      const two = screen.getByRole('checkbox', { name: 'Two' })
      await user.click(one)
      await user.click(two)
      expect(one).toBeChecked()
      expect(two).toBeChecked()
      await user.click(one)
      expect(one).not.toBeChecked()
    })

    it('switches dropdown options to dynamic expression', async () => {
      const user = userEvent.setup()
      renderBuilder(<SynFormFieldBuilder value={dropdownFieldDefinition()} onChange={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: 'Dynamic' }))
      expect(
        screen.getByText(/Default values are not available when options are populated dynamically/i)
      ).toBeInTheDocument()
      await user.type(screen.getByRole('textbox', { name: 'Dynamic options expression' }), 'steps.envs')
      expect(screen.getByRole('textbox', { name: 'Dynamic options expression' })).toHaveValue('steps.envs')
    })

    it('edits static option labels and removes an option', async () => {
      const user = userEvent.setup()
      renderBuilder(<SynFormFieldBuilder value={dropdownFieldDefinition()} onChange={vi.fn()} />)

      const displayLabel = screen.getAllByRole('textbox', { name: 'Display label' })[0]
      await user.clear(displayLabel)
      await user.type(displayLabel, 'First choice')

      await user.click(screen.getByRole('button', { name: 'Remove option 2' }))
      expect(screen.getAllByRole('textbox', { name: 'Display label' })).toHaveLength(1)
    })

    it('exposes label help for field settings', () => {
      renderBuilder(<SynFormFieldBuilder value={createEmptyFormDefinition()} onChange={vi.fn()} />)
      expect(screen.getByRole('button', { name: 'More info for Field label' })).toBeInTheDocument()
    })
  })

  it('shows validation alert when value name is invalid and does not persist to parent', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const definition = parseFormDefinition({
      fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'valid_name', label: 'Title' }],
    })

    renderBuilder(<SynFormFieldBuilder value={definition} onChange={onChange} />)
    onChange.mockClear()

    const valueNameInput = screen.getByRole('textbox', { name: 'Value name' })
    await user.clear(valueNameInput)
    await user.type(valueNameInput, '1bad')

    expect(
      screen.getByText('Fix validation errors before changes are saved to the parent form.')
    ).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('shows an error when JSON Schema import is invalid', async () => {
    const user = userEvent.setup()
    renderBuilder(<SynFormFieldBuilder value={createEmptyFormDefinition()} onChange={vi.fn()} />)
    await user.click(screen.getByRole('tab', { name: 'JSON Schema' }))

    await user.click(screen.getByRole('textbox', { name: 'Import JSON Schema' }))
    await user.paste('{')
    await user.click(screen.getByRole('button', { name: 'Load into builder' }))

    expect(screen.getByText('Invalid JSON')).toBeInTheDocument()
  })
})
