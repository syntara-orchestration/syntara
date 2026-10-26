import {
  Alert,
  Button,
  Content,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  TextArea,
  Title,
} from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import type { FormDefinitionFieldServerError } from '../../../components/forms/formFieldBuilder/formDefinitionFieldServerError'
import { SynFormFieldBuilder } from '../../../components/forms/SynFormFieldBuilder'
import { useIsVersionView } from '../VersionViewContext'

import { FormPresentationOptionsSection } from './FormPresentationOptionsSection'
import { FormPromptPreviewModal } from './FormPromptPreviewModal'
import { nodeHelp } from './shared/nodeFieldHelp'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import type { TriggerFormData } from './triggerFormSchema'

type FormTriggerConfigurationFieldsProps = Readonly<{
  formDefinitionError?: { message?: string }
  serverFieldErrors?: ReadonlyArray<FormDefinitionFieldServerError>
}>

export function FormTriggerConfigurationFields({
  formDefinitionError,
  serverFieldErrors,
}: FormTriggerConfigurationFieldsProps) {
  const isVersionView = useIsVersionView()
  const { register, setValue, control } = useFormContext<TriggerFormData>()
  const formDefinition = useWatch({ control, name: 'form_definition' })
  const message = useWatch({ control, name: 'message' })
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)

  return (
    <>
      <Stack hasGutter className={nodeFormStyles.formTriggerParameters}>
        <StackItem>
          <Alert variant="info" isInline title="Form trigger" className={nodeFormStyles.compactAlert}>
            <Content component="p">Collect structured input before the workflow runs.</Content>
          </Alert>
        </StackItem>
        <StackItem>
          <Button
            variant="link"
            isInline
            className={nodeFormStyles.previewFormLink}
            onClick={() => setIsPreviewOpen(true)}
            isDisabled={isVersionView}
          >
            Preview form
          </Button>
        </StackItem>
        <StackItem>
          <FormGroup label="Message" labelHelp={nodeHelp.formPromptMessage} fieldId="form-trigger-message">
            <TextArea
              {...register('message')}
              id="form-trigger-message"
              placeholder="Please provide the details below to start this workflow"
              rows={3}
              isDisabled={isVersionView}
            />
          </FormGroup>
        </StackItem>
        <StackItem>
          <Title headingLevel="h3" size="md" id="form-trigger-form-fields">
            Form fields
          </Title>
        </StackItem>
        <StackItem>
          {formDefinitionError?.message ? (
            <FormHelperText>
              <HelperText>
                <HelperTextItem variant="error">{formDefinitionError.message}</HelperTextItem>
              </HelperText>
            </FormHelperText>
          ) : null}
          <SynFormFieldBuilder
            designOnly
            optionsMode="static-only"
            serverFieldErrors={serverFieldErrors}
            value={formDefinition ?? createEmptyFormDefinition()}
            onChange={(definition: FormDefinition) =>
              setValue('form_definition', definition, {
                shouldDirty: true,
                shouldValidate: true,
              })
            }
            isDisabled={isVersionView}
          />
        </StackItem>
        <StackItem>
          <FormPresentationOptionsSection idPrefix="form-trigger" />
        </StackItem>
      </Stack>
      <FormPromptPreviewModal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        formDefinition={formDefinition ?? createEmptyFormDefinition()}
        message={message}
      />
    </>
  )
}
