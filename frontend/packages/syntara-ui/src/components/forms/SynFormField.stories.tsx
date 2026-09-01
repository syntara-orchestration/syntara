import { Form, Button, TextInput } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'

import styles from './formStories.module.css'
import { SynForm } from './SynForm'
import { SynFormField } from './SynFormField'

const schema = z.object({ value: z.string().min(1, 'This field is required') })
type StoryFormData = z.infer<typeof schema>

function FormFieldDemo({
  label,
  hint,
  isRequired,
  showError,
}: {
  label: string
  hint?: string
  isRequired?: boolean
  showError?: boolean
}) {
  const form = useSynForm<StoryFormData>({
    schema,
    defaultValues: { value: '' },
  })
  const { handleSubmit } = form

  const onSubmit = fn()

  return (
    <Form className={styles.formStory}>
      <SynForm form={form}>
        <SynFormField<StoryFormData, 'value'>
          name="value"
          label={label}
          fieldId="demo-field"
          isRequired={isRequired}
          hint={hint}
        >
          {({ field, fieldState }) => (
            <TextInput
              id="demo-field"
              validated={fieldState.error ? 'error' : 'default'}
              value={field.value ?? ''}
              onChange={field.onChange}
              onBlur={field.onBlur}
              name={field.name}
            />
          )}
        </SynFormField>
      </SynForm>
      {showError && (
        <Button type="button" variant="secondary" onClick={handleSubmit(onSubmit)}>
          Trigger validation
        </Button>
      )}
    </Form>
  )
}

const meta: Meta<typeof SynFormField> = {
  component: SynFormField,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Base field wrapper that binds a PatternFly `FormGroup` to a react-hook-form field via `useController`. ' +
          'Accepts a render prop that receives `field` and `fieldState` for binding the inner input. ' +
          'Use the specialised wrappers (`SynTextField`, `SynTextAreaField`) for standard text inputs. ' +
          'Use `SynFormField` directly for custom controls such as selects, date pickers, or checkboxes. ' +
          'Wrap fields in `SynForm` (from `useSynForm`) so `control` can be omitted.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

/** Default field with a label and custom input via render prop. */
export const Default: Story = {
  render: () => <FormFieldDemo label="Username" />,
}

/** Required field shows an asterisk next to the label. */
export const Required: Story = {
  render: () => <FormFieldDemo label="Username" isRequired />,
}

/** Hint text shown below the field when there is no validation error. */
export const WithHint: Story = {
  render: () => (
    <FormFieldDemo
      label="Role name"
      hint="Lowercase alphanumeric with hyphens (e.g. my-custom-role)"
      isRequired
      showError
    />
  ),
}

/** Validation error replaces the hint after a failed submit. Click "Trigger validation" to see it. */
export const WithError: Story = {
  render: () => <FormFieldDemo label="Required field" isRequired showError />,
}
