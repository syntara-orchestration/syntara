import { Alert, FormGroup, HelperText, HelperTextItem, Stack, StackItem, TextArea } from '@patternfly/react-core'
import type { Activity } from '@syntara/contracts'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo } from 'react'
import { Controller, FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useWorkflowEngineDefaults } from '../hooks/useWorkflowEngineDefaults'
import { formatDuration } from '../utils/timeUtils'
import { useIsVersionView } from '../VersionViewContext'

import { approvalFormSchema, type ApprovalFormData } from './approvalFormSchema'
import {
  APPROVER_GROUPS_EMPTY,
  APPROVER_GROUPS_HELPER_TEXT,
  APPROVER_GROUPS_LABEL,
  APPROVER_GROUPS_LOADING,
  APPROVER_GROUPS_PLACEHOLDER,
  APPROVER_USERS_EMPTY,
  APPROVER_USERS_HELPER_TEXT,
  APPROVER_USERS_LABEL,
  APPROVER_USERS_LOADING,
  APPROVER_USERS_PLACEHOLDER,
} from './approverConstants'
import { ApproverMultiSelect } from './ApproverMultiSelect'
import { FallbackDecisionField } from './FallbackDecisionField'
import { ActivityNameField } from './shared/ActivityNameField'
import { DurationInput } from './shared/DurationInput'
import { zodResolver } from './shared/formSchemaUtils'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { NodeSettingsForm } from './shared/NodeSettingsForm'
import { useApprovalDecideGroups } from './useApprovalDecideGroups'
import { useApprovalDecideUsers } from './useApprovalDecideUsers'

// Approver user type
type ApproverUser = Readonly<{ id: string; username: string }>

// Component for approver users multi-select
function ApproverUsersSelect({
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
  users: ReadonlyArray<ApproverUser>
  isLoading: boolean
  validationError?: Readonly<{ message?: string }>
  isPermissionDenied?: boolean
  hasProjectContext?: boolean
}>) {
  const showFallback = !hasProjectContext || isPermissionDenied

  let placeholderText = APPROVER_USERS_PLACEHOLDER
  if (!hasProjectContext) {
    placeholderText = 'Select a project to load approval users'
  } else if (isPermissionDenied) {
    placeholderText = 'Type a username and press Enter'
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <ApproverMultiSelect<ApproverUser>
          value={value}
          onChange={onChange}
          items={users}
          isLoading={isLoading}
          validationError={validationError}
          getItemId={(item) => item.id}
          getItemValue={(item) => item.username}
          getItemLabel={(item) => item.username}
          placeholderText={placeholderText}
          emptyText={showFallback ? 'Enter usernames manually' : APPROVER_USERS_EMPTY}
          loadingText={APPROVER_USERS_LOADING}
          helperText={APPROVER_USERS_HELPER_TEXT}
          allowCustomValue={showFallback}
        />
      </StackItem>
      {!hasProjectContext && (
        <StackItem>
          <Alert variant="info" title="Project required" isInline isPlain>
            Select a project to load approval users, or enter usernames manually.
          </Alert>
        </StackItem>
      )}
      {hasProjectContext && isPermissionDenied && (
        <StackItem>
          <Alert variant="warning" title="Dropdown unavailable" isInline isPlain>
            You don&apos;t have permission to list approval users. You can still enter usernames manually.
          </Alert>
        </StackItem>
      )}
    </Stack>
  )
}

// Approver group type
type ApproverGroup = Readonly<{ id: string; name: string }>

// Component for approver groups multi-select
function ApproverGroupsSelect({
  value,
  onChange,
  groups,
  isLoading,
  validationError,
}: Readonly<{
  value: readonly string[]
  onChange: (value: string[]) => void
  groups: ReadonlyArray<ApproverGroup>
  isLoading: boolean
  validationError?: Readonly<{ message?: string }>
}>) {
  return (
    <ApproverMultiSelect<ApproverGroup>
      value={value}
      onChange={onChange}
      items={groups}
      isLoading={isLoading}
      validationError={validationError}
      getItemId={(item) => item.id}
      getItemValue={(item) => item.name}
      getItemLabel={(item) => item.name}
      placeholderText={APPROVER_GROUPS_PLACEHOLDER}
      emptyText={APPROVER_GROUPS_EMPTY}
      loadingText={APPROVER_GROUPS_LOADING}
      helperText={APPROVER_GROUPS_HELPER_TEXT}
    />
  )
}

type NodeSettings = Activity['settings']

// Data structure for form submission (name + API approval definition)
export type ApprovalFormSubmitData = {
  name: string
  approver_users?: string[] // Usernames who can approve
  approver_groups?: string[] // Group names whose members can approve
  prompt?: string
  fallback_decision?: 'approve' | 'reject'
  /** How long (in seconds) the approver has to respond. Stored in config.decision_window. */
  decision_window?: number
  settings?: NodeSettings
  metadata?: {
    [key: string]: unknown
  }
  outputs?: {
    approved?: boolean
    decided_by?: string
    decided_at?: string
    decision_notes?: string
  }
}

type ApprovalNodeFormProps = {
  onSubmit: (data: ApprovalFormSubmitData) => void
  initialData?: Partial<ApprovalFormSubmitData>
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

function ApprovalFormFields({
  onHeaderContentChange,
  validationErrors,
  projectId,
}: {
  onHeaderContentChange?: (content: ReactNode | null) => void
  validationErrors?: { approver_users?: { message?: string }; approver_groups?: { message?: string } }
  projectId?: string
}) {
  const isVersionView = useIsVersionView()
  const { register, control, setValue } = useFormContext<ApprovalFormData>()
  const decisionWindow = useWatch({ control, name: 'decision_window' })
  const { defaults } = useWorkflowEngineDefaults()
  const approvalTimeoutDefault = defaults?.timeoutSeconds.approval ?? null

  const storeProjectId = useWorkflowStore((state) => state.projectId)
  const effectiveProjectId = projectId ?? storeProjectId

  // Fetch users with approval:decide permission and all groups
  const {
    users,
    isLoading: isLoadingUsers,
    isPermissionDenied: usersPermissionDenied,
  } = useApprovalDecideUsers(effectiveProjectId)
  const { groups, isLoading: isLoadingGroups } = useApprovalDecideGroups()

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="approval-name" ariaLabel="Name" />,
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
        <FormGroup label={APPROVER_USERS_LABEL} labelHelp={nodeHelp.approverUsers} fieldId="approval-approver-users">
          <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
            <Controller
              name="approver_users"
              control={control}
              render={({ field: { value, onChange } }) => (
                <ApproverUsersSelect
                  value={value ?? []}
                  onChange={onChange}
                  users={users}
                  isLoading={isLoadingUsers}
                  validationError={validationErrors?.approver_users}
                  isPermissionDenied={usersPermissionDenied}
                  hasProjectContext={!!effectiveProjectId}
                />
              )}
            />
          </fieldset>
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup label={APPROVER_GROUPS_LABEL} fieldId="approval-approver-groups" labelHelp={nodeHelp.approverGroups}>
          <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
            <Controller
              name="approver_groups"
              control={control}
              render={({ field: { value, onChange } }) => (
                <ApproverGroupsSelect
                  value={value ?? []}
                  onChange={onChange}
                  groups={groups}
                  isLoading={isLoadingGroups}
                  validationError={validationErrors?.approver_groups}
                />
              )}
            />
          </fieldset>
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup label="Message" labelHelp={nodeHelp.approvalMessage} fieldId="approval-prompt">
          <TextArea
            {...register('prompt')}
            id="approval-prompt"
            placeholder="Please approve this deployment to production"
            rows={3}
            isDisabled={isVersionView}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FallbackDecisionField />
      </StackItem>
      <StackItem>
        <FormGroup
          label="Decision window"
          labelHelp={nodeHelp.approvalDecisionWindow}
          fieldId="approval-decision-window"
        >
          <Stack hasGutter>
            <StackItem>
              <DurationInput
                value={decisionWindow}
                onChange={(val) => setValue('decision_window', val, { shouldDirty: true })}
                idPrefix="approval-decision-window"
                isDisabled={isVersionView}
              />
            </StackItem>
            <StackItem>
              <HelperText>
                <HelperTextItem>
                  {approvalTimeoutDefault !== null
                    ? `How long the approver has to respond before the request expires. Falls back to system default (${formatDuration(approvalTimeoutDefault)}) if not set.`
                    : 'How long the approver has to respond before the request expires. Falls back to system default if not set.'}
                </HelperTextItem>
              </HelperText>
            </StackItem>
          </Stack>
        </FormGroup>
      </StackItem>
    </Stack>
  )

  const settingsContent = (
    <NodeSettingsForm
      supportsTimeout={false}
      supportsRetryPolicy={false}
      continueOnFailureHelp="When enabled and the approval cannot complete (decision window expired or send failure), the workflow proceeds. The outcome is determined by the fallback decision in the approval config."
    />
  )

  return <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function ApprovalNodeForm(props: ApprovalNodeFormProps) {
  const defaultValues: ApprovalFormData = {
    name: props.initialData?.name ?? '',
    approver_users: props.initialData?.approver_users ?? [],
    approver_groups: props.initialData?.approver_groups ?? [],
    prompt: props.initialData?.prompt ?? '',
    fallback_decision: props.initialData?.fallback_decision ?? 'reject',
    decision_window: props.initialData?.decision_window,
    settings: props.initialData?.settings ?? {},
  }

  const handleSubmit = (data: ApprovalFormData) => {
    props.onSubmit({
      name: data.name.trim(),
      approver_users: data.approver_users && data.approver_users.length > 0 ? data.approver_users : undefined,
      approver_groups: data.approver_groups && data.approver_groups.length > 0 ? data.approver_groups : undefined,
      prompt: data.prompt?.trim() || '',
      fallback_decision: data.fallback_decision,
      decision_window: data.decision_window,
      settings: data.settings,
    })
  }

  const methods = useForm<ApprovalFormData>({
    resolver: zodResolver(approvalFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, handleSubmit)

  const {
    formState: { errors },
  } = methods

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="approval-node-form" onSubmit={methods.handleSubmit(handleSubmit)}>
        <ApprovalFormFields
          onHeaderContentChange={props.onHeaderContentChange}
          validationErrors={errors}
          projectId={props.projectId}
        />
      </NodeFormContainer>
    </FormProvider>
  )
}
