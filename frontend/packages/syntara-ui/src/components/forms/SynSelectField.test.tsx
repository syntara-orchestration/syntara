import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { z } from 'zod'

import { renderWithForm } from '../../test/renderWithForm'

import { SynSelectField } from './SynSelectField'

const schema = z.object({
  projectId: z.string().min(1, 'Project is required'),
})
type FormData = z.infer<typeof schema>

const options = [
  { value: 'proj-1', label: 'Project One' },
  { value: 'proj-2', label: 'Project Two' },
]

describe('SynSelectField', () => {
  it('renders label and placeholder', () => {
    renderWithForm<FormData>({ schema, defaultValues: { projectId: '' } }, ({ control }) => (
      <SynSelectField name="projectId" control={control} label="Project" options={options} fieldId="project-id" />
    ))

    expect(screen.getByText('Project')).toBeInTheDocument()
    expect(screen.getByLabelText('Project')).toHaveAttribute('id', 'project-id')
    expect(screen.getByLabelText('Project')).toHaveTextContent('Select an option')
  })

  it('selects an option and updates the toggle label', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { projectId: '' } }, ({ control }) => (
      <SynSelectField name="projectId" control={control} label="Project" options={options} />
    ))

    await user.click(screen.getByLabelText('Project'))
    await user.click(screen.getByRole('option', { name: 'Project Two' }))

    expect(screen.getByLabelText('Project')).toHaveTextContent('Project Two')
  })

  it('shows the selected option label for a pre-filled value', () => {
    renderWithForm<FormData>({ schema, defaultValues: { projectId: 'proj-1' } }, ({ control }) => (
      <SynSelectField name="projectId" control={control} label="Project" options={options} />
    ))

    expect(screen.getByLabelText('Project')).toHaveTextContent('Project One')
  })

  it('uses a custom placeholder', () => {
    renderWithForm<FormData>({ schema, defaultValues: { projectId: '' } }, ({ control }) => (
      <SynSelectField
        name="projectId"
        control={control}
        label="Project"
        options={options}
        placeholder="Choose a project"
      />
    ))

    expect(screen.getByLabelText('Project')).toHaveTextContent('Choose a project')
  })

  it('disables the select when isDisabled is true', () => {
    renderWithForm<FormData>({ schema, defaultValues: { projectId: '' } }, ({ control }) => (
      <SynSelectField name="projectId" control={control} label="Project" options={options} isDisabled />
    ))

    expect(screen.getByLabelText('Project')).toBeDisabled()
  })

  it('does not select disabled options', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { projectId: '' } }, ({ control }) => (
      <SynSelectField
        name="projectId"
        control={control}
        label="Project"
        options={[{ value: 'proj-1', label: 'Project One', isDisabled: true }]}
      />
    ))

    await user.click(screen.getByLabelText('Project'))
    await user.click(screen.getByRole('option', { name: 'Project One' }))

    expect(screen.getByLabelText('Project')).toHaveTextContent('Select an option')
  })

  it('shows validation error on submit', async () => {
    const user = userEvent.setup()
    renderWithForm<FormData>({ schema, defaultValues: { projectId: '' } }, ({ control, handleSubmit }) => (
      <>
        <SynSelectField name="projectId" control={control} label="Project" options={options} isRequired />
        <button type="button" onClick={handleSubmit(vi.fn())}>
          Submit
        </button>
      </>
    ))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(await screen.findByText('Project is required')).toBeInTheDocument()
  })

  it('has no accessibility violations in default state', async () => {
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { projectId: 'proj-1' } },
      ({ control }) => <SynSelectField name="projectId" control={control} label="Project" options={options} />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in error state', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>(
      { schema, defaultValues: { projectId: '' } },
      ({ control, handleSubmit }) => (
        <>
          <SynSelectField name="projectId" control={control} label="Project" options={options} isRequired />
          <button type="button" onClick={handleSubmit(vi.fn())}>
            Submit
          </button>
        </>
      )
    )

    await user.click(screen.getByRole('button', { name: 'Submit' }))
    await screen.findByText('Project is required')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when menu is open', async () => {
    const user = userEvent.setup()
    const { container } = renderWithForm<FormData>({ schema, defaultValues: { projectId: '' } }, ({ control }) => (
      <SynSelectField name="projectId" control={control} label="Project" options={options} />
    ))

    await user.click(screen.getByLabelText('Project'))

    expect(await axe(container)).toHaveNoViolations()
  })
})
