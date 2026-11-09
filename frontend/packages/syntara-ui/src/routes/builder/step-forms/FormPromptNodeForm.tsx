import { Alert, Button, Content, FormGroup, Stack, StackItem, TextArea, Title } from '@patternfly/react-core'
import type { Activity } from '@syntara/contracts'
import type { FormEvent, ReactNode } from 'react'
import { use, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Controller, FormProvider, useFormContext, useWatch } from 'react-hook-form'

import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import type { FormDefinitionFieldServerError } from '../../../components/forms/formFieldBuilder/formDefinitionFieldServerError'
import { SynFormFieldBuilder } from '../../../components/forms/SynFormFieldBuilder'
import { FORM_PREVIEW_INCOMPLETE_TOOLTIP, isFormDefinitionReadyForPreview } from '../../../forms'
import { useSynForm } from '../../../hooks/useSynForm'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { detachPromise } from '../../../utils/detachPromise'
import { useEffectiveFormDefinitionServerValidationErrors } from '../hooks/useEffectiveFormDefinitionServerValidationErrors'
import { StepEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useStepEditorAutoSubmit'
import { useWorkflowEngineDefaults } from '../hooks/useWorkflowEngineDefaults'
import { partitionFormTriggerServerValidationErrors } from '../utils/partitionFormTriggerServerValidationErrors'
import { useIsVersionView } from '../VersionViewContext'

import { ApproverMultiSelect } from './ApproverMultiSelect'
import { FormPromptFormOptionsSection } from './FormPromptFormOptionsSection'
import { getFormPromptNodeFormDefaultValues } from './formPromptNodeFormDefaults'
import { formPromptFormSchema, type FormPromptFormData } from './formPromptNodeFormSchema'
import { mapFormPromptFormDataToSubmit } from './formPromptNodeFormSubmit'
import { FormPromptPreviewModal } from './FormPromptPreviewModal'
import {
  FORM_PROMPT_STEP_INTRO_DESCRIPTION,
  RESPONDER_GROUPS_EMPTY,
  RESPONDER_GROUPS_HELPER_TEXT,
  RESPONDER_GROUPS_LABEL,
  RESPONDER_GROUPS_LOADING,
  RESPONDER_GROUPS_PLACEHOLDER,
  RESPONDER_USERS_EMPTY,
  RESPONDER_USERS_HELPER_TEXT,
  RESPONDER_USERS_LABEL,
  RESPONDER_USERS_LOADING,
  RESPONDER_USERS_PLACEHOLDER,
} from './formPromptResponderConstants'
import { FormPromptTimeoutSection } from './FormPromptTimeoutSection'
import { ActivityNameField } from './shared/ActivityNameField'
import {
  FormFieldBuilderCommitRefContext,
  type FormFieldBuilderCommitHandlers,
} from './shared/formFieldBuilderCommitRefContext'
import { stepHelp } from './shared/stepFieldHelp'
import { StepFormContainer } from './shared/StepFormContainer'
import stepFormStyles from './shared/stepFormStyles.module.css'
import { StepFormTabsLayout } from './shared/StepFormTabsLayout'
import { StepSettingsForm } from './shared/StepSettingsForm'
import { useApprovalDecideGroups } from './useApprovalDecideGroups'
import { useFormPromptSubmitUsers } from './useFormPromptSubmitUsers'

type NodeSettings = Activity['settings']

export type FormPromptFormSubmitData = {
  name: string
  message?: string | null
  /** UI-only routing hint when loading legacy definitions; not persisted on save. */
  fallback_behavior?: 'fail' | 'fallback' | null
  form_definition: FormPromptFormData['form_definition']
  responder_users?: string[]
  responder_groups?: string[]
  response_window?: number | null
  fallback_decision?: 'submit' | 'fallback' | null
  submit_label?: string | null
  success_message?: string | null
  css_override?: string | null
  settings?: NodeSettings
}

type FormPromptNodeFormProps = {
  onSubmit: (data: FormPromptFormSubmitData) => void
  initialData?: Partial<FormPromptFormSubmitData>
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
  serverValidationErrors?: ReadonlyArray<{ fieldPath?: string | null; message: string }>
}

type ResponderUser = Readonly<{ id: string; username: string }>
type ResponderGroup = Readonly<{ id: string; name: string }>

function ResponderUsersSelect({
  value,
  onChange,
  users,
  isLoading,
  validationError,
  isPermissionDenied,
  hasProjectContext,
}: Readonly<{
  value: readonly string[]
  onChange: (value: string[]) => void
  users: ReadonlyArray<ResponderUser>
  isLoading: boolean
  validationError?: Readonly<{ message?: string }>
  isPermissionDenied?: boolean
  hasProjectContext?: boolean
}>) {
  const showFallback = !hasProjectContext || isPermissionDenied

  let placeholderText = RESPONDER_USERS_PLACEHOLDER
  if (!hasProjectContext) {
    placeholderText = 'Select a project to load responder users'
  } else if (isPermissionDenied) {
    placeholderText = 'Type a username and press Enter'
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <ApproverMultiSelect<ResponderUser>
          value={value}
          onChange={onChange}
          items={users}
          isLoading={isLoading}
          validationError={validationError}
          getItemId={(item) => item.id}
          getItemValue={(item) => item.username}
          getItemLabel={(item) => item.username}
          placeholderText={placeholderText}
          emptyText={showFallback ? 'Enter usernames manually' : RESPONDER_USERS_EMPTY}
          loadingText={RESPONDER_USERS_LOADING}
          helperText={RESPONDER_USERS_HELPER_TEXT}
          allowCustomValue={showFallback}
        />
      </StackItem>
      {!hasProjectContext && (
        <StackItem>
          <Alert variant="info" title="Project required" isInline isPlain>
            Select a project to load responder users, or enter usernames manually.
          </Alert>
        </StackItem>
      )}
      {hasProjectContext && isPermissionDenied && (
        <StackItem>
          <Alert variant="warning" title="Dropdown unavailable" isInline isPlain>
            You don&apos;t have permission to list responder users. You can still enter usernames manually.
          </Alert>
        </StackItem>
      )}
    </Stack>
  )
}

function ResponderGroupsSelect({
  value,
  onChange,
  groups,
  isLoading,
  validationError,
}: Readonly<{
  value: readonly string[]
  onChange: (value: string[]) => void
  groups: ReadonlyArray<ResponderGroup>
  isLoading: boolean
  validationError?: Readonly<{ message?: string }>
}>) {
  return (
    <ApproverMultiSelect<ResponderGroup>
      value={value}
      onChange={onChange}
      items={groups}
      isLoading={isLoading}
      validationError={validationError}
      getItemId={(item) => item.id}
      getItemValue={(item) => item.name}
      getItemLabel={(item) => item.name}
      placeholderText={RESPONDER_GROUPS_PLACEHOLDER}
      emptyText={RESPONDER_GROUPS_EMPTY}
      loadingText={RESPONDER_GROUPS_LOADING}
      helperText={RESPONDER_GROUPS_HELPER_TEXT}
    />
  )
}

function FormPromptFormFields({
  onHeaderContentChange,
  projectId,
  serverFieldErrors,
}: Readonly<{
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
  serverFieldErrors?: ReadonlyArray<FormDefinitionFieldServerError>
}>) {
  const isVersionView = useIsVersionView()
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const { register, control, setValue } = useFormContext<FormPromptFormData>()
  const formDefinition = useWatch({ control, name: 'form_definition' })
  const message = useWatch({ control, name: 'message' })
  const submitLabel = useWatch({ control, name: 'submit_label' })
  const cssOverrideSource = useWatch({ control, name: 'css_override' })
  const builderCommitRef = use(FormFieldBuilderCommitRefContext)
  const storeProjectId = useWorkflowStore((state) => state.projectId)
  const effectiveProjectId = projectId ?? storeProjectId
  const {
    users,
    isLoading: isLoadingUsers,
    isPermissionDenied: usersPermissionDenied,
  } = useFormPromptSubmitUsers(effectiveProjectId)
  const { groups, isLoading: isLoadingGroups } = useApprovalDecideGroups()

  const nameField = useMemo(
    () => <ActivityNameField control={control} fieldId="form-prompt-name" ariaLabel="Name" />,
    [control]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const registerBuilderCommit = useCallback(
    (handlers: FormFieldBuilderCommitHandlers | null) => {
      if (builderCommitRef) {
        builderCommitRef.current = handlers
      }
    },
    [builderCommitRef]
  )

  const resolvedDefinition = formDefinition ?? createEmptyFormDefinition()
  const previewReady = useMemo(() => isFormDefinitionReadyForPreview(resolvedDefinition), [resolvedDefinition])
  const previewBlocked = isVersionView || !previewReady

  const parametersContent = (
    <Stack hasGutter>
      <StackItem>
        <Alert variant="info" isInline title="Form" className={stepFormStyles.compactAlert}>
          <Content component="p">{FORM_PROMPT_STEP_INTRO_DESCRIPTION}</Content>
        </Alert>
      </StackItem>
      <StackItem>
        <DisabledWithTooltip isDisabled={!isVersionView && !previewReady} content={FORM_PREVIEW_INCOMPLETE_TOOLTIP}>
          <Button
            variant="link"
            isInline
            className={stepFormStyles.previewFormLink}
            isAriaDisabled={previewBlocked}
            onClick={previewBlocked ? undefined : () => setIsPreviewOpen(true)}
          >
            Preview form
          </Button>
        </DisabledWithTooltip>
      </StackItem>
      <StackItem>
        <FormGroup
          label={RESPONDER_USERS_LABEL}
          labelHelp={stepHelp.formPromptResponderUsers}
          fieldId="form-prompt-responder-users"
        >
          <fieldset disabled={isVersionView} className={stepFormStyles.disabledFieldset}>
            <Controller
              name="responder_users"
              control={control}
              render={({ field: { value, onChange }, fieldState }) => (
                <ResponderUsersSelect
                  value={value ?? []}
                  onChange={onChange}
                  users={users}
                  isLoading={isLoadingUsers}
                  validationError={fieldState.error}
                  isPermissionDenied={usersPermissionDenied}
                  hasProjectContext={Boolean(effectiveProjectId)}
                />
              )}
            />
          </fieldset>
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup
          label={RESPONDER_GROUPS_LABEL}
          labelHelp={stepHelp.formPromptResponderGroups}
          fieldId="form-prompt-responder-groups"
        >
          <fieldset disabled={isVersionView} className={stepFormStyles.disabledFieldset}>
            <Controller
              name="responder_groups"
              control={control}
              render={({ field: { value, onChange }, fieldState }) => (
                <ResponderGroupsSelect
                  value={value ?? []}
                  onChange={onChange}
                  groups={groups}
                  isLoading={isLoadingGroups}
                  validationError={fieldState.error}
                />
              )}
            />
          </fieldset>
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup label="Message" labelHelp={stepHelp.formPromptMessage} fieldId="form-prompt-message">
          <TextArea
            {...register('message')}
            id="form-prompt-message"
            placeholder="Please provide the details below to continue"
            rows={3}
            isDisabled={isVersionView}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <Title headingLevel="h3" size="md" id="form-prompt-form-fields">
          Form fields
        </Title>
      </StackItem>
      <StackItem>
        <SynFormFieldBuilder
          designOnly
          draftMode
          serverFieldErrors={serverFieldErrors}
          value={resolvedDefinition}
          onChange={(definition) =>
            setValue('form_definition', definition, {
              shouldDirty: true,
              shouldValidate: false,
            })
          }
          registerCommit={registerBuilderCommit}
          isDisabled={isVersionView}
          previewSubmitLabel={submitLabel}
          previewCssOverrideSource={cssOverrideSource}
          previewDescription={message}
        />
      </StackItem>
      <StackItem>
        <FormPromptFormOptionsSection />
      </StackItem>
      <StackItem>
        <FormPromptTimeoutSection />
      </StackItem>
    </Stack>
  )

  const settingsContent = (
    <StepSettingsForm
      supportsRetryPolicy={false}
      supportsTimeout={false}
      continueOnFailureHelp="Controls whether the workflow continues after this form expires. When continuing, the fallback decision selects the next path."
    />
  )

  return (
    <>
      <StepFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
      <FormPromptPreviewModal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        formDefinition={resolvedDefinition}
        message={message}
        submitLabel={submitLabel}
        cssOverrideSource={cssOverrideSource}
      />
    </>
  )
}

export function FormPromptNodeForm(props: Readonly<FormPromptNodeFormProps>) {
  const { onSubmit, initialData, onHeaderContentChange, projectId, serverValidationErrors } = props
  const { defaults } = useWorkflowEngineDefaults()
  const defaultValues = getFormPromptNodeFormDefaultValues(initialData)
  const systemContinueOnFailure = defaults?.continueOnFailure ?? null
  const builderHandlersRef = useRef<FormFieldBuilderCommitHandlers | null>(null)

  const form = useSynForm({
    schema: formPromptFormSchema,
    defaultValues,
  })

  const formDefinition = useWatch({ control: form.control, name: 'form_definition' })
  const readPreparedFormDefinition = useCallback(() => builderHandlersRef.current?.readPreparedDefinition(), [])
  const effectiveServerValidationErrors = useEffectiveFormDefinitionServerValidationErrors(
    formDefinition,
    serverValidationErrors,
    { readPreparedDefinition: readPreparedFormDefinition }
  )

  const formDefinitionFieldErrors = useMemo(
    () => partitionFormTriggerServerValidationErrors(effectiveServerValidationErrors).formFieldErrors,
    [effectiveServerValidationErrors]
  )

  const syncFormDefinitionFromBuilder = useCallback(() => {
    const handlers = builderHandlersRef.current
    if (!handlers) {
      return
    }
    handlers.flush()
    const prepared = handlers.readPreparedDefinition()
    form.setValue('form_definition', prepared, { shouldDirty: true, shouldValidate: false })
  }, [form])

  const handleSubmit = useCallback(
    (data: FormPromptFormData) => {
      onSubmit(mapFormPromptFormDataToSubmit(data, systemContinueOnFailure))
    },
    [onSubmit, systemContinueOnFailure]
  )

  const submitWithFlush = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      syncFormDefinitionFromBuilder()
      detachPromise(form.handleSubmit(handleSubmit)(event))
    },
    [form, handleSubmit, syncFormDefinitionFromBuilder]
  )

  const autoSubmitRef = use(StepEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, handleSubmit, syncFormDefinitionFromBuilder)

  return (
    <FormFieldBuilderCommitRefContext.Provider value={builderHandlersRef}>
      <FormProvider {...form}>
        <StepFormContainer formId="form-prompt-step-form" onSubmit={submitWithFlush}>
          <FormPromptFormFields
            onHeaderContentChange={onHeaderContentChange}
            projectId={projectId}
            serverFieldErrors={formDefinitionFieldErrors}
          />
        </StepFormContainer>
      </FormProvider>
    </FormFieldBuilderCommitRefContext.Provider>
  )
}
