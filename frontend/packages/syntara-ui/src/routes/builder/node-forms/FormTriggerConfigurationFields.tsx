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
import { useCallback, use, useMemo, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import type { FormDefinitionFieldServerError } from '../../../components/forms/formFieldBuilder/formDefinitionFieldServerError'
import { SynFormFieldBuilder } from '../../../components/forms/SynFormFieldBuilder'
import { FORM_PREVIEW_INCOMPLETE_TOOLTIP, isFormDefinitionReadyForPreview } from '../../../forms'
import { useIsVersionView } from '../VersionViewContext'

import { FormPresentationOptionsSection } from './FormPresentationOptionsSection'
import { FormPromptPreviewModal } from './FormPromptPreviewModal'
import { nodeHelp } from './shared/nodeFieldHelp'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import {
  TriggerFormFieldBuilderCommitRefContext,
  type TriggerFormFieldBuilderCommitHandlers,
} from './triggerFormFieldBuilderCommitContext'
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
  const builderCommitRef = use(TriggerFormFieldBuilderCommitRefContext)
  const formDefinition = useWatch({ control, name: 'form_definition' })
  const message = useWatch({ control, name: 'message' })
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)

  const registerBuilderCommit = useCallback(
    (handlers: TriggerFormFieldBuilderCommitHandlers | null) => {
      if (builderCommitRef) {
        builderCommitRef.current = handlers
      }
    },
    [builderCommitRef]
  )

  const resolvedDefinition = formDefinition ?? createEmptyFormDefinition()
  const previewReady = useMemo(() => isFormDefinitionReadyForPreview(resolvedDefinition), [resolvedDefinition])
  const previewBlocked = isVersionView || !previewReady

  return (
    <>
      <Stack hasGutter className={nodeFormStyles.formTriggerParameters}>
        <StackItem>
          <Alert variant="info" isInline title="Form trigger" className={nodeFormStyles.compactAlert}>
            <Content component="p">Collect structured input before the workflow runs.</Content>
          </Alert>
        </StackItem>
        <StackItem>
          <DisabledWithTooltip isDisabled={!isVersionView && !previewReady} content={FORM_PREVIEW_INCOMPLETE_TOOLTIP}>
            <Button
              variant="link"
              isInline
              className={nodeFormStyles.previewFormLink}
              isAriaDisabled={previewBlocked}
              onClick={previewBlocked ? undefined : () => setIsPreviewOpen(true)}
            >
              Preview form
            </Button>
          </DisabledWithTooltip>
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
            draftMode
            optionsMode="static-only"
            serverFieldErrors={serverFieldErrors}
            value={resolvedDefinition}
            onChange={(definition: FormDefinition) =>
              setValue('form_definition', definition, {
                shouldDirty: true,
                shouldValidate: false,
              })
            }
            registerCommit={registerBuilderCommit}
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
        formDefinition={resolvedDefinition}
        message={message}
      />
    </>
  )
}
