import {
  Alert,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  TextArea,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'
import { use, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Controller, useFormContext, useFormState } from 'react-hook-form'

import { AppRoute } from '../../../app/AppRoute'
import { SynForm } from '../../../components/forms/SynForm'
import { SynLink } from '../../../components/SynLink'
import { useSynForm } from '../../../hooks/useSynForm'
import { detachPromise } from '../../../utils/detachPromise'
import { useIntegrationPermissions } from '../../configuration/integrations/useIntegrationPermissions'
import { ExpandableCodeEditor } from '../components/ExpandableCodeEditor'
import { FileUpload, type UploadedFile } from '../components/file-upload'
import { StepEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useStepEditorAutoSubmit'
import { DroppableField } from '../panels/fields/DroppableField'
import { useIsVersionView } from '../VersionViewContext'

import { AIAgentFileContext } from './aiAgentFileContext'
import { AIAgentFileUploadSection } from './AIAgentFileUploadSection'
import { aiAgentFormSchema, type AIAgentFormData } from './aiAgentFormSchema'
import { LLMSection, NO_PROJECT_MESSAGE, ToolsLoadError } from './AIAgentFormSections'
import {
  cleanStaleToolSelections,
  formatStaleToolsWarning,
  getToolSelection,
  getVisibleToolSelection,
  groupToolsByIntegration,
  useToolSelection,
} from './aiAgentToolSelection'
import { ConnectionsSection } from './ConnectionsSection'
import { ActivityNameField } from './shared/ActivityNameField'
import { stepHelp } from './shared/stepFieldHelp'
import { StepFormContainer } from './shared/StepFormContainer'
import stepFormStyles from './shared/stepFormStyles.module.css'
import { StepFormTabsLayout } from './shared/StepFormTabsLayout'
import { StepSettingsForm } from './shared/StepSettingsForm'
import type { IntegrationWithTools, ToolSelection } from './ToolsMultiSelect'
import { ToolsMultiSelect } from './ToolsMultiSelect'
import { useAllEnabledMcpIntegrations } from './useAllEnabledMcpIntegrations'
import { useAllTools } from './useAllTools'
import { useFilesMetadata } from './useFilesMetadata'
import type { MarkPersistedFn } from './useFileUploadState'

export type { AIAgentFormData }

/** Submitted data includes file IDs from uploads and parsed response schema */
export type AIAgentFormSubmitData = {
  fileIds: string[]
  parsedResponseSchema?: Record<string, unknown>
} & AIAgentFormData

/** Initial data for form fields (file IDs handled separately by parent) */
export type AIAgentFormInitialData = Partial<AIAgentFormData>

export type AIAgentStepFormProps = {
  /**
   * Persist the form. Return `false` (or throw) when persist fails so session
   * uploads stay DELETEable. `void` / `true` means success.
   */
  onSubmit: (data: AIAgentFormSubmitData) => boolean | void | Promise<boolean | void>
  initialData?: AIAgentFormInitialData
  existingFileIds?: string[]
  onHeaderContentChange?: (content: ReactNode | null) => void
  /** Project ID to scope integration and credential queries to this project. */
  projectId?: string
}

function FieldError({ message }: Readonly<{ message: string | undefined }>) {
  if (!message) return null
  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
          {message}
        </HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}

type AIAgentFormFieldsProps = Readonly<{
  onHeaderContentChange?: (content: ReactNode | null) => void
  initialToolSelection: ToolSelection
  projectId?: string
  integrations: IntegrationWithTools[]
  isLoadingIntegrations: boolean
  isToolsError: boolean
  onRetryTools: () => void
  hasExistingFiles: boolean
  hasNoIntegrations: boolean
}>

function AIAgentFormFields({
  onHeaderContentChange,
  initialToolSelection,
  projectId,
  integrations,
  isLoadingIntegrations,
  isToolsError,
  onRetryTools,
  hasExistingFiles,
  hasNoIntegrations,
}: AIAgentFormFieldsProps) {
  const isVersionView = useIsVersionView()
  const { register, control, getValues, setValue } = useFormContext<AIAgentFormData>()
  const { toolSelection, handleToolSelectionChange } = useToolSelection(control, setValue)
  const { errors } = useFormState({ control })
  const { canCreate: canCreateIntegration } = useIntegrationPermissions()
  const fileContext = use(AIAgentFileContext)
  if (!fileContext) throw new Error('AIAgentFormFields must be used within AIAgentFileContext.Provider')
  const { isFilesError } = fileContext

  const { selection: visibleToolSelection, staleToolInfo } = useMemo(
    () => getVisibleToolSelection(toolSelection, integrations, isLoadingIntegrations, isToolsError),
    [toolSelection, integrations, isLoadingIntegrations, isToolsError]
  )
  const { staleToolInfo: initialStaleToolInfo } = useMemo(
    () => getVisibleToolSelection(initialToolSelection, integrations, isLoadingIntegrations, isToolsError),
    [initialToolSelection, integrations, isLoadingIntegrations, isToolsError]
  )

  const staleToolsWarning = formatStaleToolsWarning((staleToolInfo ?? initialStaleToolInfo)?.removedCount)

  const nameField = useMemo(
    () => <ActivityNameField control={control} fieldId="agent-name" placeholder="Enter agent name" ariaLabel="Name" />,
    [control]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const parametersContent = (
    <Stack hasGutter>
      <LLMSection isVersionView={isVersionView} projectId={projectId} />
      <StackItem>
        <FormGroup label="Prompt" labelHelp={stepHelp.aiPrompt} fieldId="agent-prompt" isRequired>
          <DroppableField
            onDropText={(text) => {
              const current = getValues('prompt')
              setValue('prompt', (current ?? '') + text)
            }}
          >
            <TextArea
              {...register('prompt')}
              id="agent-prompt"
              placeholder="Natural language instructions for the agent..."
              rows={3}
              validated={errors.prompt ? 'error' : 'default'}
              isDisabled={isVersionView}
            />
          </DroppableField>
          <FieldError message={errors.prompt?.message} />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup label="Tools" labelHelp={stepHelp.aiTools} fieldId="agent-tools">
          <ToolsMultiSelect
            value={visibleToolSelection}
            onChange={handleToolSelectionChange}
            integrations={integrations}
            isLoading={isLoadingIntegrations}
            hasNoIntegrations={hasNoIntegrations}
          />
          {staleToolsWarning && <Alert variant="warning" isInline isPlain title={staleToolsWarning} />}
          {hasNoIntegrations && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem>
                  {canCreateIntegration ? (
                    <>
                      An administrator must{' '}
                      <SynLink to={AppRoute.Configuration.Integrations.Configure}>
                        configure an MCP server integration
                      </SynLink>{' '}
                      before tools can be selected.
                    </>
                  ) : (
                    'An administrator must configure an MCP server integration before tools can be selected.'
                  )}
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          )}
          {isToolsError && <ToolsLoadError onRetry={onRetryTools} />}
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup label="Connections" labelHelp={stepHelp.aiConnections} fieldId="agent-connections">
          <Controller
            control={control}
            name="integration_connections"
            render={({ field }) => (
              <ConnectionsSection
                integrations={integrations}
                toolSelection={toolSelection}
                integrationConnections={field.value ?? []}
                onConnectionChange={field.onChange}
                projectId={projectId}
              />
            )}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup label="Response schema" labelHelp={stepHelp.aiResponseSchema} fieldId="agent-response-schema">
          <Controller
            control={control}
            name="responseSchema"
            render={({ field }) => (
              <ExpandableCodeEditor
                code={field.value ?? ''}
                onCodeChange={field.onChange}
                language="json"
                height="150px"
                modalTitle="Edit response schema"
                ariaLabel="Response schema editor"
                isReadOnly={isVersionView}
              />
            )}
          />
          <FormHelperText>
            <HelperText>
              <HelperTextItem>Optional JSON Schema to enforce structured output format.</HelperTextItem>
            </HelperText>
          </FormHelperText>
          <FieldError message={errors.responseSchema?.message} />
        </FormGroup>
      </StackItem>
      {isFilesError && (
        <StackItem>
          <Alert
            variant="warning"
            isInline
            isPlain
            title="Previously attached files could not be loaded. They will be removed if you save."
          />
        </StackItem>
      )}
      <StackItem>
        <FormGroup label="Context file upload" labelHelp={stepHelp.aiContext} fieldId="agent-context">
          {projectId ? (
            <AIAgentFileUploadSection
              projectId={projectId}
              isVersionView={isVersionView}
              hasExistingFiles={hasExistingFiles}
              fileContext={fileContext}
            />
          ) : (
            <>
              <fieldset disabled className={stepFormStyles.disabledFieldset}>
                <FileUpload
                  files={[]}
                  onFilesSelected={() => {}}
                  onFileRemove={() => {}}
                  acceptedMimeTypes={['.pdf', '.doc', '.docx', '.txt', '.md']}
                  aria-label="Context file upload"
                  disabled
                  disabledTooltip={NO_PROJECT_MESSAGE}
                />
              </fieldset>
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>{NO_PROJECT_MESSAGE}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            </>
          )}
        </FormGroup>
      </StackItem>
    </Stack>
  )

  const settingsContent = <StepSettingsForm timeoutStepType="agentic" supportsRetryPolicy={false} />

  return <StepFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function AIAgentStepForm(props: Readonly<AIAgentStepFormProps>) {
  const { tools: allTools, isLoading: isLoadingTools, isError: isToolsError, refetch: refetchTools } = useAllTools()

  const {
    integrations: allMcpIntegrations,
    isLoading: isLoadingIntegrationsQuery,
    isError: isIntegrationsError,
    refetch: refetchIntegrations,
  } = useAllEnabledMcpIntegrations(props.projectId)

  const isLoadingIntegrations = isLoadingTools || isLoadingIntegrationsQuery
  const isAnyToolsError = isToolsError || isIntegrationsError
  const handleRetryTools = () => {
    detachPromise(refetchTools())
    detachPromise(refetchIntegrations())
  }

  const integrations = useMemo<IntegrationWithTools[]>(
    () => groupToolsByIntegration(allTools, allMcpIntegrations),
    [allTools, allMcpIntegrations]
  )
  const hasNoIntegrations = integrations.length === 0 && !isLoadingIntegrations

  const { data: hydratedFiles, isError: isFilesError } = useFilesMetadata(props.existingFileIds)
  const [userFiles, setUserFiles] = useState<UploadedFile[]>([])
  const [removedIds, setRemovedIds] = useState<Set<string>>(new Set())
  const [markPersisted, setMarkPersisted] = useState<MarkPersistedFn | null>(null)
  const deletingFileIdsRef = useRef<Set<string>>(new Set())

  const onMarkPersistedReady = useCallback((fn: MarkPersistedFn | null) => {
    // Functional update so a function value is stored, not invoked as a setState updater.
    setMarkPersisted(() => fn)
  }, [])

  const onDeletingFileIdsChange = useCallback((ids: Set<string>) => {
    deletingFileIdsRef.current = ids
  }, [])

  const completedFiles = useMemo(() => {
    const userIds = new Set(userFiles.map((f) => f.id))
    const visibleHydrated = hydratedFiles.filter((f) => !removedIds.has(f.id) && !userIds.has(f.id))
    return [...visibleHydrated, ...userFiles]
  }, [hydratedFiles, userFiles, removedIds])

  const addFiles = useCallback((files: UploadedFile[]) => {
    setUserFiles((prev) => [...prev, ...files])
  }, [])

  const removeFile = useCallback((fileId: string) => {
    setUserFiles((prev) => prev.filter((f) => f.id !== fileId))
    setRemovedIds((prev) => new Set(prev).add(fileId))
  }, [])

  const removeFilesByName = useCallback(
    (names: Set<string>) => {
      setUserFiles((prev) => prev.filter((f) => !names.has(f.file.name)))
      setRemovedIds((prev) => {
        const next = new Set(prev)
        for (const f of hydratedFiles) {
          if (names.has(f.file.name)) next.add(f.id)
        }
        return next
      })
    },
    [hydratedFiles]
  )

  const defaultValues: AIAgentFormData = {
    name: '',
    llm_model_id: '',
    prompt: '',
    tool_selection_strategy: 'NONE',
    tool_selections: [],
    integration_connections: [],
    credential_id: undefined,
    settings: {},
    ...props.initialData,
  }

  const { onSubmit: onSubmitProp } = props
  const handleSubmit = useCallback(
    async (data: AIAgentFormData) => {
      const cleanedData = cleanStaleToolSelections(data, integrations, isLoadingIntegrations, isAnyToolsError)

      const trimmed = data.responseSchema?.trim()
      const parsedResponseSchema = trimmed ? (JSON.parse(trimmed) as Record<string, unknown>) : undefined

      const currentDeletingIds = deletingFileIdsRef.current
      const fileIds: string[] = completedFiles
        .filter((f) => f.status === 'success' && !currentDeletingIds.has(f.id))
        .map((f) => f.id)

      try {
        const result = onSubmitProp({ ...cleanedData, fileIds, parsedResponseSchema })
        const outcome = result instanceof Promise ? await result : result
        if (outcome === false) {
          return false
        }
        markPersisted?.(fileIds)
        return true
      } catch {
        return false
      }
    },
    [completedFiles, integrations, isAnyToolsError, isLoadingIntegrations, onSubmitProp, markPersisted]
  )

  const form = useSynForm({
    schema: aiAgentFormSchema,
    defaultValues,
    mode: 'onChange',
    reValidateMode: 'onChange',
  })

  const onFormSubmit = useCallback((e: React.FormEvent) => form.handleSubmit(handleSubmit)(e), [form, handleSubmit])

  const autoSubmitRef = use(StepEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, handleSubmit)

  const fileContextValue = useMemo(
    () => ({
      completedFiles,
      addFiles,
      removeFile,
      removeFilesByName,
      isFilesError: isFilesError && !!props.existingFileIds?.length,
      onMarkPersistedReady,
      onDeletingFileIdsChange,
    }),
    [
      completedFiles,
      addFiles,
      removeFile,
      removeFilesByName,
      isFilesError,
      props.existingFileIds,
      onMarkPersistedReady,
      onDeletingFileIdsChange,
    ]
  )

  return (
    <AIAgentFileContext.Provider value={fileContextValue}>
      <SynForm form={form}>
        <StepFormContainer formId="ai-agent-step-form" onSubmit={onFormSubmit}>
          <AIAgentFormFields
            onHeaderContentChange={props.onHeaderContentChange}
            initialToolSelection={getToolSelection(
              defaultValues.tool_selection_strategy,
              defaultValues.tool_selections
            )}
            projectId={props.projectId}
            integrations={integrations}
            isLoadingIntegrations={isLoadingIntegrations}
            isToolsError={isAnyToolsError}
            onRetryTools={handleRetryTools}
            hasExistingFiles={!!props.existingFileIds?.length}
            hasNoIntegrations={hasNoIntegrations}
          />
        </StepFormContainer>
      </SynForm>
    </AIAgentFileContext.Provider>
  )
}
