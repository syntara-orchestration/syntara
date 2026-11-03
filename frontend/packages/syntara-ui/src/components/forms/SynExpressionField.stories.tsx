import { Button, Form } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { fn } from 'storybook/test'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'

import styles from './formStories.module.css'
import { SynExpressionField } from './SynExpressionField'
import { SynForm } from './SynForm'

const schema = z.object({
  expression: z.string().min(1, 'Expression is required'),
})
type StoryFormData = z.infer<typeof schema>

function ExpressionFieldDemo({
  hint,
  isRequired,
  isDisabled,
  showError,
  defaultValue,
}: {
  hint?: string
  isRequired?: boolean
  isDisabled?: boolean
  showError?: boolean
  defaultValue?: string
}) {
  const form = useSynForm<StoryFormData>({
    schema,
    defaultValues: { expression: defaultValue ?? '' },
  })
  const { handleSubmit } = form

  return (
    <Form className={styles.formStory}>
      <SynForm form={form}>
        <SynExpressionField
          name="expression"
          label="Condition"
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

const meta: Meta<typeof SynExpressionField> = {
  component: SynExpressionField,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'An expression text input bound to a react-hook-form string field. Combines ' +
          '`SynFormField` + PatternFly `TextInput` with drag-and-drop token support and ' +
          'inline `${...}` syntax validation. Wrap fields in `SynForm` (from `useSynForm`) ' +
          'so `control` can be omitted.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <ExpressionFieldDemo />,
}

export const WithValue: Story = {
  render: () => <ExpressionFieldDemo defaultValue='${upstream.output["status"]}' />,
}

export const Required: Story = {
  render: () => <ExpressionFieldDemo isRequired showError />,
}

export const WithHint: Story = {
  render: () => (
    <ExpressionFieldDemo hint="Enter a value or drag a field from the builder tree." isRequired showError />
  ),
}

export const Disabled: Story = {
  render: () => <ExpressionFieldDemo isDisabled defaultValue='${upstream.output["status"]}' />,
}
