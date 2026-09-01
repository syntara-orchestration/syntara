import { Button, Form } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'

import styles from './formStories.module.css'
import { SynForm } from './SynForm'
import { SynTextField } from './SynTextField'

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  email: z.string().email('Enter a valid email address'),
})
type StoryFormData = z.infer<typeof schema>

function TextFieldDemo({
  hint,
  isRequired,
  isDisabled,
  placeholder,
  showError,
}: {
  hint?: string
  isRequired?: boolean
  isDisabled?: boolean
  placeholder?: string
  showError?: boolean
}) {
  const form = useSynForm<StoryFormData>({
    schema,
    defaultValues: { name: '', email: '' },
  })
  const { handleSubmit } = form

  const onSubmit = fn()

  return (
    <Form className={styles.formStory}>
      <SynForm form={form}>
        <SynTextField<StoryFormData, 'name'>
          name="name"
          label="Group name"
          isRequired={isRequired}
          placeholder={placeholder}
          hint={hint}
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

const meta: Meta<typeof SynTextField> = {
  component: SynTextField,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'A single-line text input bound to a react-hook-form field. Combines `SynFormField` + ' +
          'PatternFly `TextInput` with all RHF bindings pre-wired. ' +
          'Wrap fields in `SynForm` (from `useSynForm`) so `control` can be omitted.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Basic text field with a label. */
export const Default: Story = {
  render: () => <TextFieldDemo placeholder="Enter group name" />,
}

/** Required field with an asterisk and placeholder. */
export const Required: Story = {
  render: () => <TextFieldDemo isRequired placeholder="Enter group name" />,
}

/** Hint text shown below the field when there is no error. Click "Trigger validation" to see the hint replaced by an error. */
export const WithHint: Story = {
  render: () => <TextFieldDemo isRequired hint="Lowercase alphanumeric with hyphens (e.g. my-group)" showError />,
}

/** Validation error displayed after a failed submit. Click "Trigger validation" to see it. */
export const WithError: Story = {
  render: () => <TextFieldDemo isRequired showError />,
}

/** Disabled field — user cannot interact with the input. */
export const Disabled: Story = {
  render: () => <TextFieldDemo isDisabled placeholder="Enter group name" />,
}
