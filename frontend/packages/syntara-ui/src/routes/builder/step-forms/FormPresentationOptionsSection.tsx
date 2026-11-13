import { FormGroup, Stack, StackItem, TextArea, TextInput, Title } from '@patternfly/react-core'
import { useFormContext } from 'react-hook-form'

import { useIsVersionView } from '../VersionViewContext'

import { stepHelp } from './shared/stepFieldHelp'
import stepFormStyles from './shared/stepFormStyles.module.css'

export type FormPresentationFormFields = {
  submit_label?: string | null
  success_message?: string | null
}

type FormPresentationOptionsSectionProps = Readonly<{
  idPrefix: string
}>

export function FormPresentationOptionsSection({ idPrefix }: FormPresentationOptionsSectionProps) {
  const isVersionView = useIsVersionView()
  const { register } = useFormContext<FormPresentationFormFields>()

  return (
    <Stack hasGutter className={stepFormStyles.formPresentationSection}>
      <StackItem>
        <Title headingLevel="h3" size="md">
          Form options
        </Title>
      </StackItem>
      <StackItem>
        <FormGroup
          label="Submit button label"
          labelHelp={stepHelp.formPromptSubmitLabel}
          fieldId={`${idPrefix}-submit-label`}
        >
          <TextInput {...register('submit_label')} id={`${idPrefix}-submit-label`} isDisabled={isVersionView} />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup
          label="Success message"
          labelHelp={stepHelp.formPromptSuccessMessage}
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
    </Stack>
  )
}
