import {
  Flex,
  FlexItem,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Label,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  TextArea,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import { ExecutorTypeEnum } from '@syntara/contracts'
import React, { type ReactNode, use, useEffect, useMemo, useRef, useState } from 'react'
import { Controller, FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form'

import { SynSelect } from '../../../components/SynSelect'
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
import { HttpCredentialSection, HttpUrlField, type ActionFormMethods } from './httpCredentialSection'
import { KeyValueFields } from './KeyValueFields'
import { ActivityNameField } from './shared/ActivityNameField'
import { zodResolver } from './shared/formSchemaUtils'
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

type ScriptEnvironmentVariablesProps = {
  register: ReturnType<typeof useFormContext<ActionFormValues>>['register']
  getValues: ReturnType<typeof useFormContext<ActionFormValues>>['getValues']
  setValue: ReturnType<typeof useFormContext<ActionFormValues>>['setValue']
  errors: { parameters?: { message?: string } }
  isDisabled: boolean
}

function ScriptEnvironmentVariables({
  register,
  getValues,
  setValue,
  errors,
  isDisabled,
}: ScriptEnvironmentVariablesProps) {
  return (
    <FormGroup label="Environment variables" labelHelp={nodeHelp.scriptEnvVars} fieldId="action-parameters">
      <DroppableField
        onDropText={(text) => {
          const current = getValues('parameters')
          setValue('parameters', (current ?? '') + text)
        }}
      >
        <TextArea
          {...register('parameters')}
          id="action-parameters"
          placeholder='{"MY_VAR": "value"}'
          rows={3}
          isDisabled={isDisabled}
          validated={errors.parameters ? 'error' : 'default'}
        />
      </DroppableField>
      <FormHelperText>
        <HelperText>
          <HelperTextItem {...(errors.parameters && { icon: <RhUiErrorIcon />, variant: 'error' as const })}>
            {errors.parameters?.message ?? 'Environment variables available during script execution'}
          </HelperTextItem>
        </HelperText>
      </FormHelperText>
    </FormGroup>
  )
}

/** Script + API form fields (Stack content) for action node. */
type ActionParametersContentProps = Readonly<{
  register: ActionFormMethods['register']
  control: ActionFormMethods['control']
  getValues: ActionFormMethods['getValues']
  setValue: ActionFormMethods['setValue']
  errors: { code?: { message?: string }; url?: { message?: string }; parameters?: { message?: string } }
  executor: ActionFormValues['executor']
  scriptEditorRef?: React.RefObject<ExpandableCodeEditorHandle | null>
  editorLanguage: CodeLanguage
  projectId?: string
}>

function ActionParametersContent(props: ActionParametersContentProps) {
  const { register, control, getValues, setValue, errors, executor, scriptEditorRef, editorLanguage, projectId } = props
  const isVersionView = useIsVersionView()

  return (
    <Stack hasGutter style={{ paddingInline: 'var(--pf-t--global--spacer--xs)' }}>
      <input type="hidden" {...register('executor')} />
      {executor === ExecutorTypeEnum.SCRIPT && (
        <>
          <StackItem>
            <FormGroup label="Language" labelHelp={nodeHelp.scriptLanguage} fieldId="action-language">
              <Controller
                control={control}
                name="language"
                render={({ field }) => (
                  <ScriptLanguageSelect
                    value={field.value ?? 'python'}
                    onChange={field.onChange}
                    isDisabled={isVersionView}
                  />
                )}
              />
            </FormGroup>
          </StackItem>
          <StackItem>
            <FormGroup label="Script" labelHelp={nodeHelp.scriptCode} isRequired fieldId="action-code">
              <Controller
                control={control}
                name="code"
                render={({ field }) => (
                  <div
                    style={
                      errors.code
                        ? {
                            borderBottom: '2px solid var(--pf-t--global--color--status--danger--default)',
                          }
                        : undefined
                    }
                  >
                    <ExpandableCodeEditor
                      ref={scriptEditorRef ?? undefined}
                      code={field.value ?? ''}
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
              />
              <FormHelperText>
                <HelperText>
                  <HelperTextItem {...(errors.code && { icon: <RhUiErrorIcon />, variant: 'error' as const })}>
                    {errors.code?.message ?? 'Script code to execute'}
                  </HelperTextItem>
                </HelperText>
              </FormHelperText>
            </FormGroup>
          </StackItem>
          <StackItem>
            <ScriptEnvironmentVariables
              register={register}
              getValues={getValues}
              setValue={setValue}
              errors={errors}
              isDisabled={isVersionView}
            />
          </StackItem>
        </>
      )}
      {executor === ExecutorTypeEnum.HTTP_REQUEST && (
        <>
          <HttpCredentialSection
            control={control}
            register={register}
            getValues={getValues}
            setValue={setValue}
            urlError={errors.url}
            isVersionView={isVersionView}
            projectId={projectId}
          />
          <StackItem>
            <FormGroup label="HTTP Method" labelHelp={nodeHelp.httpMethod} fieldId="action-method">
              <Controller
                control={control}
                name="method"
                render={({ field }) => (
                  <HttpMethodSelect value={field.value ?? 'GET'} onChange={field.onChange} isDisabled={isVersionView} />
                )}
              />
            </FormGroup>
          </StackItem>
          <StackItem>
            <Controller
              control={control}
              name="headers"
              render={({ field }) => (
                <KeyValueFields
                  entries={field.value ?? []}
                  onChange={field.onChange}
                  isDisabled={isVersionView}
                  labelHelp={nodeHelp.httpHeaders}
                />
              )}
            />
          </StackItem>
          <StackItem>
            <FormGroup label="Body" labelHelp={nodeHelp.httpBody} fieldId="action-body">
              <DroppableField
                onDropText={(text) => {
                  const current = getValues('body')
                  setValue('body', (current ?? '') + text)
                }}
              >
                <TextArea
                  {...register('body')}
                  id="action-body"
                  placeholder='{"key": "value"}'
                  rows={3}
                  isDisabled={isVersionView}
                />
              </DroppableField>
            </FormGroup>
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
    register,
    control,
    getValues,
    setValue,
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
          <ActivityNameField<ActionFormValues>
            register={register}
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
    [register, executor]
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
      register={register}
      control={control}
      getValues={getValues}
      setValue={setValue}
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

  const methods = useForm<ActionFormValues>({
    resolver: zodResolver(actionFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, handleSubmit)

  const {
    formState: { errors },
  } = methods
  const scriptEditorRef = useRef<ExpandableCodeEditorHandle | null>(null)

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="action-node-form" onSubmit={methods.handleSubmit(handleSubmit)}>
        <ActionFormFields
          onHeaderContentChange={props.onHeaderContentChange}
          validationErrors={errors}
          scriptEditorRef={scriptEditorRef}
          projectId={props.projectId}
        />
      </NodeFormContainer>
    </FormProvider>
  )
}
