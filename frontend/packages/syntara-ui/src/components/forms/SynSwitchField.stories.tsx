import { Form } from '@patternfly/react-core'
import type { Meta, StoryObj } from '@storybook/tanstack-react'
import { z } from 'zod'

import { useSynForm } from '../../hooks/useSynForm'

import styles from './formStories.module.css'
import { SynForm } from './SynForm'
import { SynSwitchField } from './SynSwitchField'

const schema = z.object({
  enabled: z.boolean(),
})
type StoryFormData = z.infer<typeof schema>

function SwitchFieldDemo({
  hint,
  isDisabled,
  defaultEnabled,
}: {
  hint?: string
  isDisabled?: boolean
  defaultEnabled?: boolean
}) {
  const form = useSynForm<StoryFormData>({
    schema,
    defaultValues: { enabled: defaultEnabled ?? false },
  })

  return (
    <Form className={styles.formStory}>
      <SynForm form={form}>
        <SynSwitchField name="enabled" label="Enable feature" hint={hint} isDisabled={isDisabled} />
      </SynForm>
    </Form>
  )
}

const meta: Meta<typeof SynSwitchField> = {
  component: SynSwitchField,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'A boolean switch bound to a react-hook-form field. Combines `SynFormField` + ' +
          'PatternFly `Switch` with RHF bindings pre-wired. ' +
          'Wrap fields in `SynForm` (from `useSynForm`) so `control` can be omitted.',
      },
    },
  },
}
export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <SwitchFieldDemo />,
}

export const Enabled: Story = {
  render: () => <SwitchFieldDemo defaultEnabled />,
}

export const WithHint: Story = {
  render: () => <SwitchFieldDemo hint="Turn on to allow access for all authenticated users." />,
}

export const Disabled: Story = {
  render: () => <SwitchFieldDemo isDisabled defaultEnabled />,
}
