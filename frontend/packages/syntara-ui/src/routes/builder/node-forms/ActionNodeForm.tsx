import {
  Flex,
  FlexItem,
  Label,
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
import type { ActionFormData as RegistryActionFormData } from '../hooks/useNodeCreation'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { DroppableField } from '../panels/fields/DroppableField'
import { useIsVersionView } from '../VersionViewContext'

import { actionFormSchema, type ActionFormData, type ActionFormValues } from './actionFormSchema'
import { HttpCredentialSection, HttpUrlField } from './httpCredentialSection'
import { KeyValueFields } from './KeyValueFields'
import { ActivityNameField } from './shared/ActivityNameField'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { NodeSettingsForm } from './shared/NodeSettingsForm'

// Re-export schema type for form state; registry uses useNodeCreation.ActionFormData
export type { ActionFormData }
export { HttpUrlField }
export type { HttpUrlFieldProps } from './httpCredentialSection'
export type ExecutorType = ActionFormData['executor']
export type ScriptLanguage = 'python' | 'bash'
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

type ActionNodeFormProps = {
  onSubmit: (data: RegistryActionFormData) => void
  initialData?: Partial<RegistryActionFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

const SCRIPT_LANGUAGE_OPTIONS: Array<{ label: string; value: ScriptLanguage }> = [
  { label: 'Python', value: 'python' },
  { label: 'Bash', value: 'bash' },
]

const HTTP_METHOD_OPTIONS: Array<{ label: HttpMethod; value: HttpMethod }> = [
  { label: 'GET', value: 'GET' },
  { label: 'POST', value: 'POST' },
  { label: 'PUT', value: 'PUT' },
  { label: 'PATCH', value: 'PATCH' },
  { label: 'DELETE', value: 'DELETE' },
]

function ScriptLanguageSelect({
  value,
  onChange,
  isDisabled,
}: {
  value: string
  onChange: (value: string) => void
  isDisabled?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = SCRIPT_LANGUAGE_OPTIONS.find((o) => o.value === value)?.label
  return (
    <SynSelect
      id="action-language"
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
          aria-label="Language"
        >
          {selectedLabel ?? value}
        </MenuToggle>
      )}
    >
      <SelectList>
        {SCRIPT_LANGUAGE_OPTIONS.map((o) => (
          <SelectOption key={o.value} value={o.value}>
            {o.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

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
      labelHelp={nodeHelp.scriptEnvVars}
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

/** Script + API form fields (Stack content) for action node. */
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
    <Stack hasGutter style={{ paddingInline: 'var(--pf-t--global--spacer--xs)' }}>
      <input type="hidden" {...register('executor')} />
      {executor === ExecutorTypeEnum.SCRIPT && (
        <>
          <StackItem>
            <SynFormField
              name="language"
              label="Language"
              labelHelp={nodeHelp.scriptLanguage}
              fieldId="action-language"
            >
              {({ field }) => (
                <ScriptLanguageSelect
                  value={typeof field.value === 'string' ? field.value : 'python'}
                  onChange={field.onChange}
                  isDisabled={isVersionView}
                />
              )}
            </SynFormField>
          </StackItem>
          <StackItem>
            <SynFormField
              name="code"
              label="Script"
              labelHelp={nodeHelp.scriptCode}
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
            <SynFormField name="method" label="HTTP Method" labelHelp={nodeHelp.httpMethod} fieldId="action-method">
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
                  labelHelp={nodeHelp.httpHeaders}
                />
              )}
            </SynFormField>
          </StackItem>
          <StackItem>
            <SynFormField name="body" label="Body" labelHelp={nodeHelp.httpBody} fieldId="action-body" hideFooter>
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
  const language = useWatch({ control, name: 'language' })
  const editorLanguage: 'bash' | 'python' | 'plaintext' =
    language === 'bash' || language === 'python' ? language : 'plaintext'

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
        {executor === ExecutorTypeEnum.SCRIPT && (
          <FlexItem>
            <Label isCompact color="orange" style={{ fontSize: 'var(--pf-t--global--font--size--sm)' }}>
              Developer Preview
            </Label>
          </FlexItem>
        )}
      </Flex>
    ),
    [control, executor]
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
  const timeoutNodeType = isHttpRequest ? 'http_request' : 'script'
  const settingsContent = <NodeSettingsForm timeoutNodeType={timeoutNodeType} supportsRetryPolicy={isHttpRequest} />

  return <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function ActionNodeForm(props: Readonly<ActionNodeFormProps>) {
  const defaultValues: ActionFormValues = {
    name: '',
    executor: props.initialData?.executor ?? ExecutorTypeEnum.SCRIPT,
    code: '',
    url: '',
    language: 'python',
    method: 'GET',
    settings: {},
    ...props.initialData,
  }

  const handleSubmit = (data: ActionFormValues) => {
    // Clean up data based on executor type (schema type is assignable to registry type)
    const cleanedData: RegistryActionFormData = {
      name: data.name,
      executor: data.executor,
      language: data.executor === ExecutorTypeEnum.SCRIPT ? data.language : undefined,
      code: data.executor === ExecutorTypeEnum.SCRIPT ? data.code : undefined,
      method: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.method : undefined,
      url: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.url : undefined,
      headers: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.headers : undefined,
      body: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.body : undefined,
      parameters: data.parameters ?? undefined,
      requiresApproval: props.initialData?.requiresApproval,
      credential_id: data.credential_id ?? undefined,
      settings: {
        ...data.settings,
        retry_policy: data.executor === ExecutorTypeEnum.HTTP_REQUEST ? data.settings?.retry_policy : undefined,
      },
    }
    props.onSubmit(cleanedData)
  }

  const form = useSynForm({
    schema: actionFormSchema,
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, handleSubmit)

  const {
    formState: { errors },
  } = form
  const scriptEditorRef = useRef<ExpandableCodeEditorHandle | null>(null)

  return (
    <NodeFormContainer formId="action-node-form" onSubmit={form.handleSubmit(handleSubmit)}>
      <SynForm form={form}>
        <ActionFormFields
          onHeaderContentChange={props.onHeaderContentChange}
          validationErrors={errors}
          scriptEditorRef={scriptEditorRef}
          projectId={props.projectId}
        />
      </SynForm>
    </NodeFormContainer>
  )
}
