import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { getFileUploadInput } from '../../test/getFileUploadInput'
import { renderWithForm } from '../../test/renderWithForm'

import { SynFileField } from './SynFileField'

const schema = z.object({
  file: z
    .instanceof(File, { message: 'Workflow file is required' })
    .optional()
    .refine((value) => value instanceof File, 'Workflow file is required'),
})
type FormData = z.infer<typeof schema>

describe('SynFileField', () => {
  it('renders label and upload control', () => {
    renderWithForm<FormData>({ schema, defaultValues: { file: undefined } }, ({ control }) => (
      <SynFileField name="file" control={control} label="Workflow file" />
    ))

    expect(screen.getByText('Workflow file')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument()
  })

  it('binds an uploaded file to the form field', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>({ schema, defaultValues: { file: undefined } }, ({ control }) => (
      <SynFileField name="file" control={control} label="Workflow file" />
    ))

    const file = new File(['{"name":"demo"}'], 'workflow.json', { type: 'application/json' })
    await user.upload(getFileUploadInput(container), file)

    expect(screen.getByDisplayValue('workflow.json')).toBeInTheDocument()
  })

  it('clears the selected file when clear is clicked', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>({ schema, defaultValues: { file: undefined } }, ({ control }) => (
      <SynFileField name="file" control={control} label="Workflow file" />
    ))

    const file = new File(['{"name":"demo"}'], 'workflow.json', { type: 'application/json' })
    await user.upload(getFileUploadInput(container), file)
    expect(screen.getByDisplayValue('workflow.json')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear' }))

    expect(screen.queryByDisplayValue('workflow.json')).not.toBeInTheDocument()
  })

  it('renders custom upload labels', () => {
    renderWithForm<FormData>({ schema, defaultValues: { file: undefined } }, ({ control }) => (
      <SynFileField
        name="file"
        control={control}
        label="Workflow file"
        browseButtonText="Browse files"
        filenamePlaceholder="Choose a JSON workflow"
      />
    ))

    expect(screen.getByRole('button', { name: 'Browse files' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Choose a JSON workflow')).toBeInTheDocument()
  })

  it('disables the upload control when isDisabled is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { file: undefined } }, ({ control }) => (
      <SynFileField name="file" control={control} label="Workflow file" isDisabled />
    ))

    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled()
  })

  it('shows hint text when provided', () => {
    renderWithForm<FormData>({ schema, defaultValues: { file: undefined } }, ({ control }) => (
      <SynFileField name="file" control={control} label="Workflow file" hint="Upload a JSON workflow file." />
    ))

    expect(screen.getByText('Upload a JSON workflow file.')).toBeInTheDocument()
  })

  it('ignores non-file form values when rendering the upload control', () => {
    const looseSchema = z.object({
      file: z.any(),
    })

    renderWithForm({ schema: looseSchema, defaultValues: { file: 'not-a-file' } }, ({ control }) => (
      <SynFileField name="file" control={control} label="Workflow file" />
    ))

    expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument()
    expect(screen.queryByDisplayValue('not-a-file')).not.toBeInTheDocument()
  })

  it('shows validation error on submit when no file is selected', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { file: undefined } }, ({ control, handleSubmit }) => (
      <>
        <SynFileField name="file" control={control} label="Workflow file" isRequired />
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Workflow file is required')).toBeInTheDocument()
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderWithForm<FormData>({ schema, defaultValues: { file: undefined } }, ({ control }) => (
      <SynFileField name="file" control={control} label="Workflow file" />
    ))

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { file: undefined } },
      ({ control, handleSubmit }) => (
        <>
          <SynFileField name="file" control={control} label="Workflow file" isRequired />
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Workflow file is required')

    expect(await axe(container)).toHaveNoViolations()
  })
})
