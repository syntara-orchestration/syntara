import { Alert, Button, Content, FormGroup, Stack, StackItem, TextArea, Title } from '@patternfly/react-core'
import type { Activity } from '@syntara/contracts'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo, useState } from 'react'
import { Controller, FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { SynFormFieldBuilder } from '../../../components/forms/SynFormFieldBuilder'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useWorkflowEngineDefaults } from '../hooks/useWorkflowEngineDefaults'
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
import { zodResolver } from './shared/formSchemaUtils'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { NodeSettingsForm } from './shared/NodeSettingsForm'
import { useApprovalDecideGroups } from './useApprovalDecideGroups'
import { useApprovalDecideUsers } from './useApprovalDecideUsers'

type NodeSettings = Activity['settings']

export type FormPromptFormSubmitData = {
  name: string
  message?: string | null
  form_definition: FormPromptFormData['form_definition']
  responder_users?: string[]
  responder_groups?: string[]
  response_window?: number | null
  fallback_decision?: 'submit' | 'fallback' | null
  fallback_behavior?: 'fail' | 'fallback'
  submit_label?: string | null
  success_message?: string | null
  timezone?: string | null
  css_override?: string | null
  settings?: NodeSettings
}

type FormPromptNodeFormProps = {
  onSubmit: (data: FormPromptFormSubmitData) => void
  initialData?: Partial<FormPromptFormSubmitData>
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
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
    placeholderText = 'Select a project to load users'
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
            Select a project to scope this workflow, or enter usernames manually.
          </Alert>
        </StackItem>
      )}
      {hasProjectContext && isPermissionDenied && (
        <StackItem>
          <Alert variant="info" title="User directory" isInline isPlain>
            User search is not available yet. Enter usernames manually for now.
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
}: Readonly<{
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}>) {
  const isVersionView = useIsVersionView()
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const { register, control, setValue } = useFormContext<FormPromptFormData>()
  const formDefinition = useWatch({ control, name: 'form_definition' })
  const message = useWatch({ control, name: 'message' })
  const storeProjectId = useWorkflowStore((state) => state.projectId)
  const effectiveProjectId = projectId ?? storeProjectId
  const {
    users,
    isLoading: isLoadingUsers,
    isPermissionDenied: usersPermissionDenied,
  } = useApprovalDecideUsers(effectiveProjectId)
  const { groups, isLoading: isLoadingGroups } = useApprovalDecideGroups()

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="form-prompt-name" ariaLabel="Name" />,
    [register]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const parametersContent = (
    <Stack hasGutter>
      <StackItem>
        <Alert variant="info" isInline title="Form" className={nodeFormStyles.compactAlert}>
          <Content component="p">{FORM_PROMPT_STEP_INTRO_DESCRIPTION}</Content>
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
        <FormGroup
          label={RESPONDER_USERS_LABEL}
          labelHelp={nodeHelp.formPromptResponderUsers}
          fieldId="form-prompt-responder-users"
        >
          <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
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
          labelHelp={nodeHelp.formPromptResponderGroups}
          fieldId="form-prompt-responder-groups"
        >
          <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
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
        <FormGroup label="Message" fieldId="form-prompt-message">
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
          value={formDefinition ?? createEmptyFormDefinition()}
          onChange={(definition) =>
            setValue('form_definition', definition as FormPromptFormData['form_definition'], {
              shouldDirty: true,
              shouldValidate: true,
            })
          }
          isDisabled={isVersionView}
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
    <NodeSettingsForm
      supportsRetryPolicy={false}
      continueOnFailureHideFieldLabel
      continueOnFailureHelp="Controls whether the workflow continues after this form expires. When continuing, the fallback decision selects the next path."
      timeoutFormat="seconds"
      timeoutSectionTitle=""
      timeoutLabel="Expected duration (seconds)"
      timeoutDefaultSeconds={600}
      timeoutHelp="Show a 'Running long' warning after this duration. Does not stop the run. System default: 10m."
    />
  )

  return (
    <>
      <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
      <FormPromptPreviewModal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        formDefinition={formDefinition ?? createEmptyFormDefinition()}
        message={message}
      />
    </>
  )
}

export function FormPromptNodeForm(props: FormPromptNodeFormProps) {
  const { defaults } = useWorkflowEngineDefaults()
  const defaultValues = getFormPromptNodeFormDefaultValues(props.initialData)
  const systemContinueOnFailure = defaults?.continueOnFailure ?? null

  const handleSubmit = (data: FormPromptFormData) => {
    props.onSubmit(mapFormPromptFormDataToSubmit(data, systemContinueOnFailure))
  }

  const methods = useForm<FormPromptFormData>({
    resolver: zodResolver(formPromptFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, handleSubmit)

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="form-prompt-node-form" onSubmit={methods.handleSubmit(handleSubmit)}>
        <FormPromptFormFields onHeaderContentChange={props.onHeaderContentChange} projectId={props.projectId} />
      </NodeFormContainer>
    </FormProvider>
  )
}
