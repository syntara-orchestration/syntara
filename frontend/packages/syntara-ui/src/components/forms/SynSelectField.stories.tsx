import { Button, Form } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { fn } from 'storybook/test'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'

import styles from './formStories.module.css'
import { SynForm } from './SynForm'
import { SynSelectField } from './SynSelectField'

const schema = z.object({
  projectId: z.string().min(1, 'Project is required'),
})
type StoryFormData = z.infer<typeof schema>

const options = [
  { value: 'proj-1', label: 'Operations' },
  { value: 'proj-2', label: 'Security' },
  { value: 'proj-3', label: 'Platform', isDisabled: true },
]

function SelectFieldDemo({
  hint,
  isRequired,
  isDisabled,
  showError,
}: {
  hint?: string
  isRequired?: boolean
  isDisabled?: boolean
  showError?: boolean
}) {
  const form = useSynForm<StoryFormData>({
    schema,
    defaultValues: { projectId: '' },
  })
  const { handleSubmit } = form

  return (
    <Form className={styles.formStory}>
      <SynForm form={form}>
        <SynSelectField
          name="projectId"
          label="Project"
          options={options}
          isRequired={isRequired}
          hint={hint}
          isDisabled={isDisabled}
        />
      </SynForm>
      {showError && (
        <Button type="button" variant="secondary" onClick={handleSubmit(fn())}>
          Trigger validation
        </Button>
      )}
    </Form>
  )
}

const meta: Meta<typeof SynSelectField> = {
  component: SynSelectField,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'A single-select dropdown bound to a react-hook-form field. Combines `SynFormField` + ' +
          '`SynSelect` with MenuToggle/SelectList wiring and RHF bindings pre-wired. ' +
          'Wrap fields in `SynForm` (from `useSynForm`) so `control` can be omitted.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <SelectFieldDemo />,
}

export const Required: Story = {
  render: () => <SelectFieldDemo isRequired showError />,
}

export const WithHint: Story = {
  render: () => <SelectFieldDemo hint="Choose the project that will own this resource." isRequired showError />,
}

export const Disabled: Story = {
  render: () => <SelectFieldDemo isDisabled />,
}
