import {
  Alert,
  Button,
  Content,
  FormGroup,
  Stack,
  StackItem,
  TextArea,
  Title,
} from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useCallback, use, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { SynFormFieldBuilder } from '../../../components/forms/SynFormFieldBuilder'
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

export function FormTriggerConfigurationFields() {
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
          <SynFormFieldBuilder
            designOnly
            optionsMode="static-only"
            value={formDefinition ?? createEmptyFormDefinition()}
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
        formDefinition={formDefinition ?? createEmptyFormDefinition()}
        message={message}
      />
    </>
  )
}
