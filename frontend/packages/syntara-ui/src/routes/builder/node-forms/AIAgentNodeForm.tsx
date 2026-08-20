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
import type { IntegrationsAPI, ToolManagerAPI } from '@syntara/contracts'
import type { ReactNode } from 'react'
import { use, useCallback, useEffect, useMemo, useState } from 'react'
import type { Control, UseFormSetValue } from 'react-hook-form'
import { Controller, FormProvider, useForm, useFormContext, useFormState, useWatch } from 'react-hook-form'

import { AppRoute } from '../../../app/AppRoute'
import { SynLink } from '../../../components/SynLink'
import { detachPromise } from '../../../utils/detachPromise'
import { useIntegrationPermissions } from '../../configuration/integrations/useIntegrationPermissions'
import { ExpandableCodeEditor } from '../components/ExpandableCodeEditor'
import { FileUpload, type UploadedFile } from '../components/file-upload'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { DroppableField } from '../panels/fields/DroppableField'
import { useIsVersionView } from '../VersionViewContext'

import { AIAgentFileContext } from './aiAgentFileContext'
import { AIAgentFileUploadSection } from './AIAgentFileUploadSection'
import { aiAgentFormSchema, type AIAgentFormData } from './aiAgentFormSchema'
import { LLMSection, NO_PROJECT_MESSAGE, ToolsLoadError } from './AIAgentFormSections'
import { ConnectionsSection } from './ConnectionsSection'
import { ActivityNameField } from './shared/ActivityNameField'
import { zodResolver } from './shared/formSchemaUtils'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { NodeSettingsForm } from './shared/NodeSettingsForm'
import type { IntegrationWithTools, ToolSelection } from './ToolsMultiSelect'
import { ToolsMultiSelect } from './ToolsMultiSelect'
import { useAllEnabledMcpIntegrations } from './useAllEnabledMcpIntegrations'
import { useAllTools } from './useAllTools'
import { useFilesMetadata } from './useFilesMetadata'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']
type ToolWithParameters = ToolManagerAPI.components['schemas']['ToolWithParameters']

export type { AIAgentFormData }

/** Submitted data includes file IDs from uploads and parsed response schema */
export type AIAgentFormSubmitData = {
  fileIds: string[]
  parsedResponseSchema?: Record<string, unknown>
} & AIAgentFormData

/** Initial data for form fields (file IDs handled separately by parent) */
export type AIAgentFormInitialData = Partial<AIAgentFormData>

export type AIAgentNodeFormProps = {
  onSubmit: (data: AIAgentFormSubmitData) => void
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

function groupToolsByIntegration(tools: ToolWithParameters[], integrations: IntegrationRead[]): IntegrationWithTools[] {
  const integrationMap = new Map(
    integrations.filter((i): i is IntegrationRead & { id: string } => Boolean(i.id)).map((i) => [i.id, i.name])
  )

  const grouped = new Map<string, { name: string; tools: { id: string; name: string; description: string | null }[] }>()
  for (const tool of tools) {
    const integrationId = tool.integration_id
    if (!integrationId) continue
    if (!integrationMap.has(integrationId)) continue
    if (tool.enabled === false) continue
    if (!tool.id) continue
    if (!grouped.has(integrationId)) {
      grouped.set(integrationId, {
        name: integrationMap.get(integrationId) ?? integrationId,
        tools: [],
      })
    }
    grouped.get(integrationId)?.tools.push({
      id: tool.id,
      name: tool.namespaced_name,
      description: null,
    })
  }

  return Array.from(grouped.entries()).map(([id, { name, tools: discovered_tools }]) => ({
    id,
    name,
    discovered_tools,
  }))
}

function useToolSelection(control: Control<AIAgentFormData>, setValue: UseFormSetValue<AIAgentFormData>) {
  const toolSelectionStrategy = useWatch({ control, name: 'tool_selection_strategy' }) ?? 'NONE'
  const rawToolSelections = useWatch({ control, name: 'tool_selections' })

  const toolSelection = useMemo<ToolSelection>(() => {
    const toolSelections = rawToolSelections ?? []
    if (toolSelectionStrategy === 'ALL') return { strategy: 'ALL' }
    if (toolSelectionStrategy === 'SELECTED' && toolSelections.length > 0)
      return { strategy: 'SELECTED', toolIds: toolSelections }
    return { strategy: 'NONE' }
  }, [toolSelectionStrategy, rawToolSelections])

  const handleToolSelectionChange = useCallback(
    (selection: ToolSelection) => {
      if (selection.strategy === 'ALL') {
        setValue('tool_selection_strategy', 'ALL')
        setValue('tool_selections', [])
      } else if (selection.strategy === 'SELECTED') {
        setValue('tool_selection_strategy', 'SELECTED')
        setValue('tool_selections', selection.toolIds)
      } else {
        setValue('tool_selection_strategy', 'NONE')
        setValue('tool_selections', [])
        setValue('integration_connections', [])
      }
    },
    [setValue]
  )

  return { toolSelection, handleToolSelectionChange }
}

type AIAgentFormFieldsProps = Readonly<{
  onHeaderContentChange?: (content: ReactNode | null) => void
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

  const [staleToolsWarning, setStaleToolsWarning] = useState('')

  const nameField = useMemo(
    () => (
      <ActivityNameField register={register} fieldId="agent-name" placeholder="Enter agent name" ariaLabel="Name" />
    ),
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
      <LLMSection isVersionView={isVersionView} projectId={projectId} />
      <StackItem>
        <FormGroup label="Prompt" labelHelp={nodeHelp.aiPrompt} fieldId="agent-prompt" isRequired>
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
        <FormGroup label="Tools" labelHelp={nodeHelp.aiTools} fieldId="agent-tools">
          <ToolsMultiSelect
            value={toolSelection}
            onChange={handleToolSelectionChange}
            integrations={integrations}
            isLoading={isLoadingIntegrations}
            isError={isToolsError}
            hasNoIntegrations={hasNoIntegrations}
            onStaleDetected={({ validToolIds, removedCount }) => {
              if (validToolIds.length === 0) {
                handleToolSelectionChange({ strategy: 'NONE' })
              } else {
                handleToolSelectionChange({ strategy: 'SELECTED', toolIds: validToolIds })
              }
              const plural = removedCount > 1
              setStaleToolsWarning(
                `${String(removedCount)} previously selected tool${plural ? 's are' : ' is'} no longer available and ${plural ? 'have' : 'has'} been removed.`
              )
            }}
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
        <FormGroup label="Connections" labelHelp={nodeHelp.aiConnections} fieldId="agent-connections">
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
        <FormGroup label="Response schema" labelHelp={nodeHelp.aiResponseSchema} fieldId="agent-response-schema">
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
        <FormGroup label="Context file upload" labelHelp={nodeHelp.aiContext} fieldId="agent-context">
          {projectId ? (
            <AIAgentFileUploadSection
              projectId={projectId}
              isVersionView={isVersionView}
              hasExistingFiles={hasExistingFiles}
              fileContext={fileContext}
            />
          ) : (
            <>
              <fieldset disabled className={nodeFormStyles.disabledFieldset}>
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

  const settingsContent = <NodeSettingsForm timeoutNodeType="agentic" supportsRetryPolicy={false} />

  return <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function AIAgentNodeForm(props: Readonly<AIAgentNodeFormProps>) {
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

  const handleSubmit = (data: AIAgentFormData) => {
    // Parse response schema (already validated by Zod superRefine)
    const trimmed = data.responseSchema?.trim()
    const parsedResponseSchema = trimmed ? (JSON.parse(trimmed) as Record<string, unknown>) : undefined

    const fileIds: string[] = completedFiles.filter((f) => f.status === 'success').map((f) => f.id)

    props.onSubmit({ ...data, fileIds, parsedResponseSchema })
  }

  const methods = useForm<AIAgentFormData>({
    resolver: zodResolver(aiAgentFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
    mode: 'onChange',
    reValidateMode: 'onChange',
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, handleSubmit)

  const fileContextValue = useMemo(
    () => ({
      completedFiles,
      addFiles,
      removeFile,
      removeFilesByName,
      isFilesError: isFilesError && !!props.existingFileIds?.length,
    }),
    [completedFiles, addFiles, removeFile, removeFilesByName, isFilesError, props.existingFileIds]
  )

  return (
    <AIAgentFileContext.Provider value={fileContextValue}>
      <FormProvider {...methods}>
        <NodeFormContainer formId="ai-agent-node-form" onSubmit={methods.handleSubmit(handleSubmit)}>
          <AIAgentFormFields
            onHeaderContentChange={props.onHeaderContentChange}
            projectId={props.projectId}
            integrations={integrations}
            isLoadingIntegrations={isLoadingIntegrations}
            isToolsError={isAnyToolsError}
            onRetryTools={handleRetryTools}
            hasExistingFiles={!!props.existingFileIds?.length}
            hasNoIntegrations={hasNoIntegrations}
          />
        </NodeFormContainer>
      </FormProvider>
    </AIAgentFileContext.Provider>
  )
}
