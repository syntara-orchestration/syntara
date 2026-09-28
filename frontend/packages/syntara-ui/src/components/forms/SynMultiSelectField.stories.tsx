import { Button, Form } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { fn } from 'storybook/test'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'

import styles from './formStories.module.css'
import { SynForm } from './SynForm'
import { SynMultiSelectField } from './SynMultiSelectField'

const schema = z.object({
  roles: z.array(z.string()).min(1, 'Select at least one role'),
})
type StoryFormData = z.infer<typeof schema>

const options = [
  { value: 'admin', label: 'Administrator' },
  { value: 'auditor', label: 'Auditor' },
  { value: 'user', label: 'User' },
]

function MultiSelectFieldDemo({
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
    defaultValues: { roles: [] },
  })
  const { handleSubmit } = form

  return (
    <Form className={styles.formStory}>
      <SynForm form={form}>
        <SynMultiSelectField
          name="roles"
          label="Roles"
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

const meta: Meta<typeof SynMultiSelectField> = {
  component: SynMultiSelectField,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'A multi-select dropdown bound to a react-hook-form string-array field. Combines ' +
          '`SynFormField` + `SynSelect` with checkbox options and RHF bindings pre-wired. ' +
          'Wrap fields in `SynForm` (from `useSynForm`) so `control` can be omitted.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <MultiSelectFieldDemo />,
}

export const Required: Story = {
  render: () => <MultiSelectFieldDemo isRequired showError />,
}

export const WithHint: Story = {
  render: () => <MultiSelectFieldDemo hint="Select one or more roles to assign." isRequired showError />,
}

export const Disabled: Story = {
  render: () => <MultiSelectFieldDemo isDisabled />,
}
