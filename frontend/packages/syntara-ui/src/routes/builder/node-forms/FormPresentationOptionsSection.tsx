import { FormGroup, Stack, StackItem, TextArea, TextInput, Title } from '@patternfly/react-core'
import { Controller, useFormContext } from 'react-hook-form'

import { useIsVersionView } from '../VersionViewContext'

import { FormPromptTimezoneSelect } from './FormPromptTimezoneSelect'
import { nodeHelp } from './shared/nodeFieldHelp'

export type FormPresentationFormFields = {
  submit_label?: string | null
  success_message?: string | null
  timezone?: string | null
  css_override?: string | null
}

type FormPresentationOptionsSectionProps = Readonly<{
  idPrefix: string
}>

export function FormPresentationOptionsSection({ idPrefix }: FormPresentationOptionsSectionProps) {
  const isVersionView = useIsVersionView()
  const { register, control } = useFormContext<FormPresentationFormFields>()

  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h3" size="md">
          Form options
        </Title>
      </StackItem>
      <StackItem>
        <FormGroup
          label="Submit button label"
          labelHelp={nodeHelp.formPromptSubmitLabel}
          fieldId={`${idPrefix}-submit-label`}
        >
          <TextInput {...register('submit_label')} id={`${idPrefix}-submit-label`} isDisabled={isVersionView} />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup
          label="Success message"
          labelHelp={nodeHelp.formPromptSuccessMessage}
          fieldId={`${idPrefix}-success-message`}
        >
          <TextArea
            {...register('success_message')}
            id={`${idPrefix}-success-message`}
            rows={3}
            resizeOrientation="vertical"
            isDisabled={isVersionView}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup
          label="Timezone for date fields"
          labelHelp={nodeHelp.formPromptTimezone}
          fieldId={`${idPrefix}-timezone`}
        >
          <Controller
            control={control}
            name="timezone"
            render={({ field }) => (
              <FormPromptTimezoneSelect
                value={field.value ?? 'UTC'}
                onChange={field.onChange}
                isDisabled={isVersionView}
              />
            )}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup label="CSS override" labelHelp={nodeHelp.formPromptCssOverride} fieldId={`${idPrefix}-css-override`}>
          <TextArea
            {...register('css_override')}
            id={`${idPrefix}-css-override`}
            rows={4}
            resizeOrientation="vertical"
            isDisabled={isVersionView}
          />
        </FormGroup>
      </StackItem>
    </Stack>
  )
}
