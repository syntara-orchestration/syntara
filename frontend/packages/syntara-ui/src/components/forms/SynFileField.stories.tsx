import { Button, Form } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { fn } from 'storybook/test'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'

import styles from './formStories.module.css'
import { SynFileField } from './SynFileField'
import { SynForm } from './SynForm'

const schema = z.object({
  file: z
    .instanceof(File, { message: 'Workflow file is required' })
    .optional()
    .refine((value) => value instanceof File, 'Workflow file is required'),
})
type StoryFormData = z.infer<typeof schema>

function FileFieldDemo({
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
    defaultValues: { file: undefined },
  })
  const { handleSubmit } = form

  return (
    <Form className={styles.formStory}>
      <SynForm form={form}>
        <SynFileField
          name="file"
          label="Workflow file"
          isRequired={isRequired}
          hint={hint}
          isDisabled={isDisabled}
          dropzoneProps={{ accept: { 'application/json': ['.json'] } }}
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

const meta: Meta<typeof SynFileField> = {
  component: SynFileField,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'A file upload control bound to a react-hook-form `File | undefined` field. Combines ' +
          '`SynFormField` + PatternFly `FileUpload` with RHF bindings pre-wired. ' +
          'Wrap fields in `SynForm` (from `useSynForm`) so `control` can be omitted.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <FileFieldDemo />,
}

export const Required: Story = {
  render: () => <FileFieldDemo isRequired showError />,
}

export const WithHint: Story = {
  render: () => <FileFieldDemo hint="Upload a JSON workflow export file." isRequired showError />,
}

export const Disabled: Story = {
  render: () => <FileFieldDemo isDisabled />,
}
