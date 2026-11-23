import {
  Flex,
  FlexItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  TextArea,
} from '@patternfly/react-core'
import { ExecutorTypeEnum } from '@syntara/contracts'
import React, { type ReactNode, use, useEffect, useMemo, useRef, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynSelect } from '../../../components/SynSelect'
import { useSynForm } from '../../../hooks/useSynForm'
import {
  ExpandableCodeEditor,
  type CodeLanguage,
  type ExpandableCodeEditorHandle,
} from '../components/ExpandableCodeEditor'
import { StepEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useStepEditorAutoSubmit'
import { DroppableField } from '../panels/fields/DroppableField'
import type { ActionFormData as RegistryActionFormData } from '../stepFormTypes'
import { ScriptAffinityEnum } from '../utils/scriptExecutionProfile'
import { useIsVersionView } from '../VersionViewContext'

import { actionFormSchema, type ActionFormData, type ActionFormValues } from './actionFormSchema'
import { HttpCredentialSection, HttpUrlField } from './httpCredentialSection'
import { KeyValueFields } from './KeyValueFields'
import { ScriptExecutionTab } from './ScriptExecutionTab'
import { ActivityNameField } from './shared/ActivityNameField'
import { stepHelp } from './shared/stepFieldHelp'
import { StepFormContainer } from './shared/StepFormContainer'
import stepFormStyles from './shared/stepFormStyles.module.css'
import { StepFormTabsLayout } from './shared/StepFormTabsLayout'
import { StepSettingsForm } from './shared/StepSettingsForm'

// Re-export schema type for form state; registry uses stepFormTypes.ActionFormData
export type { ActionFormData }
export { HttpUrlField }
export type { HttpUrlFieldProps } from './httpCredentialSection'
export type ExecutorType = ActionFormData['executor']
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

type ActionStepFormProps = {
  onSubmit: (data: RegistryActionFormData) => void
  initialData?: Partial<RegistryActionFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

const HTTP_METHOD_OPTIONS: Array<{ label: HttpMethod; value: HttpMethod }> = [
  { label: 'GET', value: 'GET' },
  { label: 'POST', value: 'POST' },
  { label: 'PUT', value: 'PUT' },
  { label: 'PATCH', value: 'PATCH' },
  { label: 'DELETE', value: 'DELETE' },
]

function HttpMethodSelect({
  value,
  onChange,
  isDisabled,
}: {
  value: string
  onChange: (value: string) => void
  isDisabled?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = HTTP_METHOD_OPTIONS.find((o) => o.value === value)?.label
  return (
    <SynSelect
      id="action-method"
      isOpen={isOpen}
      selected={value || undefined}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isDisabled={isDisabled}
          aria-label="HTTP Method"
        >
          {selectedLabel ?? value}
        </MenuToggle>
      )}
    >
      <SelectList>
        {HTTP_METHOD_OPTIONS.map((o) => (
          <SelectOption key={o.value} value={o.value}>
            {o.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

function ScriptEnvironmentVariables({ isDisabled }: Readonly<{ isDisabled: boolean }>) {
  const { getValues, setValue } = useFormContext<ActionFormValues>()

  return (
    <SynFormField
      name="parameters"
      label="Environment variables"
      labelHelp={stepHelp.scriptEnvVars}
      fieldId="action-parameters"
      hint="Environment variables available during script execution"
    >
      {({ field, fieldState }) => (
        <DroppableField
          onDropText={(text) => {
            const current = getValues('parameters')
            setValue('parameters', (current ?? '') + text)
          }}
        >
          <TextArea
            id="action-parameters"
            placeholder='{"MY_VAR": "value"}'
            rows={3}
            isDisabled={isDisabled}
            validated={fieldState.error ? 'error' : 'default'}
            value={typeof field.value === 'string' ? field.value : ''}
            onChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
          />
        </DroppableField>
      )}
    </SynFormField>
  )
}

/** Script + API form fields (Stack content) for an action step. */
type ActionParametersContentProps = Readonly<{
  errors: { code?: { message?: string } }
  executor: ActionFormValues['executor']
  scriptEditorRef?: React.RefObject<ExpandableCodeEditorHandle | null>
  editorLanguage: CodeLanguage
  projectId?: string
}>

function ActionParametersContent({
  errors,
  executor,
  scriptEditorRef,
  editorLanguage,
  projectId,
}: ActionParametersContentProps) {
  const { register, getValues, setValue } = useFormContext<ActionFormValues>()
  const isVersionView = useIsVersionView()

  return (
    <Stack hasGutter className={stepFormStyles.tabContentStack}>
      <input type="hidden" {...register('executor')} />
      {(executor === ExecutorTypeEnum.SCRIPT_PYTHON || executor === ExecutorTypeEnum.SCRIPT_BASH) && (
        <>
          <StackItem>
            <SynFormField
              name="code"
              label="Script"
              labelHelp={stepHelp.scriptCode}
              isRequired
              fieldId="action-code"
              hint="Script code to execute"
            >
              {({ field, fieldState }) => (
                <div
                  style={
                    fieldState.error || errors.code
                      ? {
                          borderBottom: '2px solid var(--pf-t--global--color--status--danger--default)',
                        }
                      : undefined
                  }
                >
                  <ExpandableCodeEditor
                    ref={scriptEditorRef ?? undefined}
                    code={typeof field.value === 'string' ? field.value : ''}
                    onCodeChange={field.onChange}
                    language={editorLanguage}
                    height="200px"
                    ariaLabel="Script code editor"
                    isDarkTheme
                    isReadOnly={isVersionView}
                    onDropText={(text) => {
                      scriptEditorRef?.current?.insertAtCursor(text)
                    }}
                  />
                </div>
              )}
            </SynFormField>
          </StackItem>
          <StackItem>
            <ScriptEnvironmentVariables isDisabled={isVersionView} />
          </StackItem>
        </>
      )}
      {executor === ExecutorTypeEnum.HTTP_REQUEST && (
        <>
          <HttpCredentialSection isVersionView={isVersionView} projectId={projectId} />
          <StackItem>
            <SynFormField name="method" label="HTTP Method" labelHelp={stepHelp.httpMethod} fieldId="action-method">
              {({ field }) => (
                <HttpMethodSelect
                  value={typeof field.value === 'string' ? field.value : 'GET'}
                  onChange={field.onChange}
                  isDisabled={isVersionView}
                />
              )}
            </SynFormField>
          </StackItem>
          <StackItem>
            <SynFormField name="headers" label="" hideFormGroupLabel hideFooter>
              {({ field }) => (
                <KeyValueFields
                  entries={Array.isArray(field.value) ? field.value : []}
                  onChange={field.onChange}
                  isDisabled={isVersionView}
                  labelHelp={stepHelp.httpHeaders}
                />
              )}
            </SynFormField>
          </StackItem>
          <StackItem>
            <SynFormField name="body" label="Body" labelHelp={stepHelp.httpBody} fieldId="action-body" hideFooter>
              {({ field }) => (
                <DroppableField
                  onDropText={(text) => {
                    const current = getValues('body')
                    setValue('body', (current ?? '') + text)
                  }}
                >
                  <TextArea
                    id="action-body"
                    placeholder='{"key": "value"}'
                    rows={3}
                    isDisabled={isVersionView}
                    value={typeof field.value === 'string' ? field.value : ''}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                    name={field.name}
                  />
                </DroppableField>
              )}
            </SynFormField>
          </StackItem>
        </>
      )}
    </Stack>
  )
}

/**
 * Form fields component that manually registers fields with react-hook-form
 */
function ActionFormFields({
  onHeaderContentChange,
  validationErrors,
  scriptEditorRef,
  projectId,
}: Readonly<{
  onHeaderContentChange?: (content: ReactNode | null) => void
  validationErrors?: { code?: { message?: string }; url?: { message?: string } }
  scriptEditorRef?: React.RefObject<ExpandableCodeEditorHandle | null>
  projectId?: string
}>) {
  const {
    control,
    formState: { errors: contextErrors },
  } = useFormContext<ActionFormValues>()
  const errors = validationErrors ?? contextErrors
  const executor = useWatch({ control, name: 'executor' })
  let editorLanguage: CodeLanguage = 'plaintext'
  if (executor === ExecutorTypeEnum.SCRIPT_BASH) {
    editorLanguage = 'bash'
  } else if (executor === ExecutorTypeEnum.SCRIPT_PYTHON) {
    editorLanguage = 'python'
  }
  const isScriptExecutor = executor === ExecutorTypeEnum.SCRIPT_PYTHON || executor === ExecutorTypeEnum.SCRIPT_BASH

  useEffect(() => {
    if (errors.code && scriptEditorRef?.current) scriptEditorRef.current.focus()
  }, [errors.code, scriptEditorRef])

  const headerContent = useMemo(
    () => (
      <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
        <FlexItem>
          <ActivityNameField
            control={control}
            fieldId="action-name"
            placeholder="Enter activity name"
            ariaLabel="Name"
          />
        </FlexItem>
      </Flex>
    ),
    [control]
  )

  useEffect(() => {
    onHeaderContentChange?.(headerContent)
  }, [headerContent, onHeaderContentChange])

  useEffect(
    () => () => {
      onHeaderContentChange?.(null)
    },
    [onHeaderContentChange]
  )

  const parametersContent = (
    <ActionParametersContent
      errors={errors}
      executor={executor}
      scriptEditorRef={scriptEditorRef}
      editorLanguage={editorLanguage}
      projectId={projectId}
    />
  )

  const isHttpRequest = executor === ExecutorTypeEnum.HTTP_REQUEST
  const executionContent = isScriptExecutor ? <ScriptExecutionTab /> : undefined
  // Script timeout defaults are shared by both runtime images in the settings API.
  const timeoutStepType = isHttpRequest ? ExecutorTypeEnum.HTTP_REQUEST : 'script'
  const settingsContent = <StepSettingsForm timeoutStepType={timeoutStepType} supportsRetryPolicy={isHttpRequest} />

  return (
    <StepFormTabsLayout
      parametersContent={parametersContent}
      executionContent={executionContent}
      settingsContent={settingsContent}
    />
  )
}

export function ActionStepForm(props: Readonly<ActionStepFormProps>) {
  const defaultValues: ActionFormValues = {
    name: '',
    executor: props.initialData?.executor ?? ExecutorTypeEnum.SCRIPT_PYTHON,
    code: '',
    url: '',
    method: 'GET',
    affinity: ScriptAffinityEnum.NONE,
    settings: {},
    ...props.initialData,
  }

  const handleSubmit = (data: ActionFormValues) => {
    // Clean up data based on executor type (schema type is assignable to registry type)
    const settings = { ...data.settings }
    if (data.executor !== ExecutorTypeEnum.HTTP_REQUEST) {
      delete settings.retry_policy
    }

    const cleanedData: RegistryActionFormData = {
      name: data.name,
      executor: data.executor,
      code:
        data.executor === ExecutorTypeEnum.SCRIPT_PYTHON || data.executor === ExecutorTypeEnum.SCRIPT_BASH
          ? data.code
          : undefined,
      method: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.method : undefined,
      url: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.url : undefined,
      headers: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.headers : undefined,
      body: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.body : undefined,
      parameters: data.parameters ?? undefined,
      requiresApproval: props.initialData?.requiresApproval,
      credential_id: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.credential_id : undefined,
      affinity:
        data.executor === ExecutorTypeEnum.SCRIPT_PYTHON || data.executor === ExecutorTypeEnum.SCRIPT_BASH
          ? data.affinity
          : undefined,
      execution_target_id:
        (data.executor === ExecutorTypeEnum.SCRIPT_PYTHON || data.executor === ExecutorTypeEnum.SCRIPT_BASH) &&
        data.affinity === ScriptAffinityEnum.REQUIRED_TARGET
          ? data.execution_target_id
          : undefined,
      settings: Object.keys(settings).length > 0 ? settings : undefined,
    }
    props.onSubmit(cleanedData)
  }

  const form = useSynForm({
    schema: actionFormSchema,
    defaultValues,
  })

  const autoSubmitRef = use(StepEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, handleSubmit)

  const {
    formState: { errors },
  } = form
  const scriptEditorRef = useRef<ExpandableCodeEditorHandle | null>(null)

  return (
    <StepFormContainer formId="action-step-form" onSubmit={form.handleSubmit(handleSubmit)}>
      <SynForm form={form}>
        <ActionFormFields
          onHeaderContentChange={props.onHeaderContentChange}
          validationErrors={errors}
          scriptEditorRef={scriptEditorRef}
          projectId={props.projectId}
        />
      </SynForm>
    </StepFormContainer>
  )
}
