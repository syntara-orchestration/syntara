import { Button, Form } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'

import styles from './formStories.module.css'
import { SynForm } from './SynForm'
import { SynTextAreaField } from './SynTextAreaField'

const schema = z.object({
  description: z.string().max(2000, 'Description must be 2000 characters or fewer').optional(),
  notes: z.string().min(1, 'Notes are required'),
})
type StoryFormData = z.infer<typeof schema>

function TextAreaFieldDemo({
  name,
  label,
  hint,
  isRequired,
  isDisabled,
  placeholder,
  rows,
  showError,
}: {
  name: keyof StoryFormData
  label: string
  hint?: string
  isRequired?: boolean
  isDisabled?: boolean
  placeholder?: string
  rows?: number
  showError?: boolean
}) {
  const form = useSynForm({
    schema,
    defaultValues: { description: '', notes: '' },
  })
  const { handleSubmit } = form

  const onSubmit = fn()

  return (
    <Form className={styles.formStory}>
      <SynForm form={form}>
        <SynTextAreaField
          name={name}
          label={label}
          isRequired={isRequired}
          placeholder={placeholder}
          hint={hint}
          rows={rows}
          isDisabled={isDisabled}
        />
      </SynForm>
      {showError && (
        <Button type="button" variant="secondary" onClick={handleSubmit(onSubmit)}>
          Trigger validation
        </Button>
      )}
    </Form>
  )
}

const meta: Meta<typeof SynTextAreaField> = {
  component: SynTextAreaField,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'A multi-line text area bound to a react-hook-form field. Combines `SynFormField` + ' +
          'PatternFly `TextArea` with all RHF bindings pre-wired. ' +
          'Wrap fields in `SynForm` (from `useSynForm`) so `control` can be omitted.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Basic textarea with a label and placeholder. */
export const Default: Story = {
  render: () => <TextAreaFieldDemo name="description" label="Description" placeholder="Enter description" rows={3} />,
}

/** Required textarea with a validation error on empty submit. Click "Trigger validation". */
export const Required: Story = {
  render: () => (
    <TextAreaFieldDemo name="notes" label="Notes" isRequired placeholder="Enter notes" rows={4} showError />
  ),
}

/** Hint text shown below the field when there is no error. */
export const WithHint: Story = {
  render: () => (
    <TextAreaFieldDemo
      name="description"
      label="Description"
      hint="Up to 2000 characters"
      placeholder="Enter description"
      rows={3}
    />
  ),
}

/** Disabled textarea — user cannot interact with the field. */
export const Disabled: Story = {
  render: () => (
    <TextAreaFieldDemo name="description" label="Description" isDisabled placeholder="Enter description" rows={3} />
  ),
}
