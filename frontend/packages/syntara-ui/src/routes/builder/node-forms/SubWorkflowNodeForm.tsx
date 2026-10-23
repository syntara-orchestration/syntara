import { zodResolver } from '@hookform/resolvers/zod'
import { Alert, Button, Flex, FlexItem, Spinner, Stack, StackItem } from '@patternfly/react-core'
import { useCallback, use, useEffect, useMemo } from 'react'
import { Controller, FormProvider, useForm, useWatch, type UseFormReturn } from 'react-hook-form'
import { z } from 'zod'

import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import type { BaseNodeFormProps } from '../registry/NodeRegistry'
import { useIsVersionView } from '../VersionViewContext'

import { ChildWorkflowSelector } from './ChildWorkflowSelector'
import { InputMappingFields } from './InputMappingFields'
import {
  formatInputMappingJson,
  getInvocationInputFields,
  parseFreeformInputMapping,
  serializeInvocationInputMapping,
  type InvocationInputField,
} from './invocationSchemaUtils'
import { ActivityNameField } from './shared/ActivityNameField'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { nodeSettingsSchema } from './shared/nodeSettingsSchema'
import { SubWorkflowSettingsForm } from './SubWorkflowSettingsForm'
import {
  isInvocationSchemaForbidden,
  isInvocationSchemaNotFound,
  useChildWorkflowSelector,
  type InvocationTrigger,
} from './useChildWorkflowSelector'

const subWorkflowSettingsSchema = nodeSettingsSchema.omit({ retry_policy: true })

export type SubWorkflowFormData = {
  name: string
  workflow_id: string
  trigger_node_id: string
  input_mapping: Record<string, unknown>
  settings?: z.infer<typeof subWorkflowSettingsSchema>
}

type SubWorkflowFormValues = SubWorkflowFormData & {
  input_mapping_json: string
}

type WorkflowSelectorState = ReturnType<typeof useChildWorkflowSelector>
type SubWorkflowMethods = UseFormReturn<SubWorkflowFormValues>

const subWorkflowFormSchema = z.object({
  name: z.string().trim().min(1, 'Step name is required'),
  workflow_id: z.string(),
  trigger_node_id: z.string(),
  input_mapping: z.record(z.string(), z.unknown()),
  input_mapping_json: z.string(),
  settings: subWorkflowSettingsSchema.optional(),
})

function resolveSelectedTrigger(triggers: InvocationTrigger[], triggerNodeId: string): InvocationTrigger | undefined {
  const selectedTrigger = triggers.find((trigger) => trigger.trigger_node_id === triggerNodeId)
  if (selectedTrigger) return selectedTrigger
  return triggers.length === 1 ? triggers[0] : undefined
}

function normalizeProjectId(projectId: string | undefined): string | null {
  return projectId ?? null
}

function normalizeWorkflowId(workflowId: string): string | null {
  return workflowId || null
}

function getInvocationTriggers(invocation: WorkflowSelectorState): InvocationTrigger[] {
  return invocation.selectedSchema?.triggers ?? invocation.selectedOption?.triggers ?? []
}

function hasExplicitEmptyInputSchema(trigger?: InvocationTrigger): boolean {
  const schema = trigger?.input_schema
  if (schema?.type !== 'object') return false

  const properties = schema.properties
  return (
    typeof properties === 'object' &&
    properties !== null &&
    !Array.isArray(properties) &&
    Object.keys(properties).length === 0 &&
    schema.additionalProperties === false
  )
}

function handleWorkflowSelection(methods: SubWorkflowMethods, workflowId: string | null, triggerNodeId: string) {
  methods.setValue('workflow_id', workflowId ?? '', { shouldDirty: true, shouldValidate: true })
  methods.setValue('trigger_node_id', triggerNodeId, { shouldDirty: true, shouldValidate: true })
  // Preserve input_mapping values - serializeInvocationInputMapping filters to current schema on submit
  methods.clearErrors(['workflow_id', 'trigger_node_id', 'input_mapping', 'input_mapping_json'])
}

function handleTriggerSelection(methods: SubWorkflowMethods, triggerNodeId: string) {
  methods.setValue('trigger_node_id', triggerNodeId, { shouldDirty: true, shouldValidate: true })
  // Preserve input_mapping values - serializeInvocationInputMapping filters to current schema on submit
  methods.clearErrors(['trigger_node_id', 'input_mapping', 'input_mapping_json'])
}

function submitSubWorkflowForm(
  values: SubWorkflowFormValues,
  context: {
    onSubmit: (data: SubWorkflowFormData) => void
    methods: SubWorkflowMethods
    selectedTrigger?: InvocationTrigger
    inputFields: InvocationInputField[]
  }
): boolean {
  // Persist the current configuration, including incomplete references and mappings. The
  // database-backed workflow validator reports missing configuration after the parent is saved.
  const { methods, selectedTrigger, inputFields, onSubmit } = context

  let inputMapping: Record<string, unknown>
  try {
    if (hasExplicitEmptyInputSchema(selectedTrigger)) {
      inputMapping = {}
    } else if (inputFields.length > 0) {
      inputMapping = serializeInvocationInputMapping(values.input_mapping, inputFields)
    } else {
      inputMapping = parseFreeformInputMapping(values.input_mapping_json)
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Invalid input mapping.'
    methods.setError(inputFields.length > 0 ? 'input_mapping' : 'input_mapping_json', {
      type: 'validation',
      message,
    })
    return false
  }

  onSubmit({
    name: values.name,
    workflow_id: values.workflow_id,
    trigger_node_id: values.trigger_node_id || selectedTrigger?.trigger_node_id || '',
    input_mapping: inputMapping,
    settings: values.settings,
  })
  return true
}

function WorkflowSelectionFields({
  methods,
  invocation,
  workflowId,
  triggerNodeId,
  hasTriggers,
  isVersionView,
}: Readonly<{
  methods: SubWorkflowMethods
  invocation: WorkflowSelectorState
  workflowId: string
  triggerNodeId: string
  hasTriggers: boolean
  isVersionView: boolean
}>) {
  return (
    <Stack hasGutter>
      <StackItem>
        <Controller
          name="workflow_id"
          control={methods.control}
          render={({ field }) => (
            <ChildWorkflowSelector
              options={invocation.options}
              selectedOption={invocation.selectedOption}
              selectedWorkflowLabel={invocation.selectedWorkflowLabel}
              selectedWorkflowId={field.value || null}
              selectedTriggerNodeId={triggerNodeId}
              workflowError={methods.formState.errors.workflow_id?.message}
              triggerError={methods.formState.errors.trigger_node_id?.message}
              onWorkflowChange={(selectedWorkflowId, defaultTriggerId) =>
                handleWorkflowSelection(methods, selectedWorkflowId, defaultTriggerId)
              }
              onTriggerChange={(selectedTriggerId) => handleTriggerSelection(methods, selectedTriggerId)}
              setSearchTerm={invocation.setSearchTerm}
              isLoading={invocation.isLoading}
              hasNextPage={Boolean(invocation.hasNextPage)}
              isFetchingNextPage={invocation.isFetchingNextPage}
              onLoadMore={invocation.loadMoreWorkflows}
              hasError={invocation.hasError}
              errorMessage={invocation.errorMessage}
              errorVariant={invocation.errorVariant}
              onRetry={invocation.retryFailedLookups}
              labelHelp={nodeHelp.subworkflowWorkflow}
              triggerLabelHelp={nodeHelp.subworkflowTrigger}
              isRequired
              isDisabled={isVersionView}
            />
          )}
        />
      </StackItem>

      {workflowId && isInvocationSchemaForbidden(invocation.selectedSchemaError) && (
        <StackItem>
          <Alert variant="warning" isInline title="You do not have permission to read this child workflow.">
            <Button variant="link" type="button" onClick={() => invocation.retryFailedLookups(workflowId)}>
              Retry
            </Button>
          </Alert>
        </StackItem>
      )}
      {workflowId && isInvocationSchemaNotFound(invocation.selectedSchemaError) && (
        <StackItem>
          <Alert variant="warning" isInline title="This workflow has no published version available to invoke.">
            Publish the child workflow, then{' '}
            <Button variant="link" type="button" onClick={() => invocation.retryFailedLookups(workflowId)}>
              retry
            </Button>
            .
          </Alert>
        </StackItem>
      )}
      {workflowId && invocation.selectedSchema && (!invocation.selectedSchema.is_eligible || !hasTriggers) && (
        <StackItem>
          <Alert variant="warning" isInline title="This workflow has no eligible Sub-workflow Trigger.">
            Add a Sub-workflow Trigger to the child workflow, publish it, then{' '}
            <Button variant="link" type="button" onClick={() => invocation.retryFailedLookups(workflowId)}>
              retry
            </Button>
            .
          </Alert>
        </StackItem>
      )}
      {workflowId && invocation.selectedSchemaQuery?.isPending && (
        <StackItem>
          <Spinner size="sm" aria-label="Loading child workflow inputs" />
        </StackItem>
      )}
    </Stack>
  )
}

function WorkflowInputMapping({
  methods,
  inputFields,
  sectionTitle,
  freeformJson,
  isDisabled,
}: Readonly<{
  methods: SubWorkflowMethods
  inputFields: InvocationInputField[]
  sectionTitle: string
  freeformJson: string
  isDisabled: boolean
}>) {
  return (
    <Controller
      name="input_mapping"
      control={methods.control}
      render={({ field, fieldState }) => (
        <InputMappingFields
          fields={inputFields}
          sectionTitle={sectionTitle}
          values={field.value}
          onChange={(value) => {
            field.onChange(value)
            methods.clearErrors('input_mapping')
          }}
          freeformJson={freeformJson}
          onFreeformJsonChange={(value) => {
            methods.setValue('input_mapping_json', value, { shouldDirty: true, shouldValidate: true })
            methods.clearErrors('input_mapping_json')
          }}
          isDisabled={isDisabled}
          labelHelp={nodeHelp.subworkflowInputMapping}
          error={fieldState.error?.message ?? methods.formState.errors.input_mapping_json?.message}
        />
      )}
    />
  )
}

/** Configure a child workflow, its Subworkflow Trigger, and input mappings. */
export function SubWorkflowNodeForm({
  onSubmit,
  initialData,
  onHeaderContentChange,
  projectId,
}: BaseNodeFormProps<SubWorkflowFormData>) {
  const isVersionView = useIsVersionView()
  const methods = useForm<SubWorkflowFormValues>({
    resolver: zodResolver(subWorkflowFormSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: initialData?.name ?? '',
      workflow_id: initialData?.workflow_id ?? '',
      trigger_node_id: initialData?.trigger_node_id ?? '',
      input_mapping: initialData?.input_mapping ?? {},
      input_mapping_json: formatInputMappingJson(initialData?.input_mapping),
      settings: initialData?.settings ?? {},
    },
  })

  const { control } = methods
  const workflowId = useWatch({ control, name: 'workflow_id' })
  const triggerNodeId = useWatch({ control, name: 'trigger_node_id' })
  const freeformJson = useWatch({ control, name: 'input_mapping_json' })
  const invocation = useChildWorkflowSelector({
    projectId: normalizeProjectId(projectId),
    selectedWorkflowId: normalizeWorkflowId(workflowId),
  })
  const triggers = getInvocationTriggers(invocation)
  const selectedTrigger = resolveSelectedTrigger(triggers, triggerNodeId)
  const hasNoDeclaredInputs = hasExplicitEmptyInputSchema(selectedTrigger)
  const canConfigureInputMapping =
    Boolean(workflowId) && invocation.selectedSchema?.is_eligible === true && selectedTrigger !== undefined
  const inputFields = useMemo(
    () => getInvocationInputFields(selectedTrigger?.input_schema),
    [selectedTrigger?.input_schema]
  )
  const inputSectionTitle = 'Inputs'
  const autoSubmitRef = use(NodeEditorAutoSubmitContext)

  const submitForm = useCallback(
    (values: SubWorkflowFormValues) =>
      submitSubWorkflowForm(values, { onSubmit, methods, selectedTrigger, inputFields }),
    [inputFields, methods, onSubmit, selectedTrigger]
  )
  useRegisterAutoSubmit(autoSubmitRef, methods, submitForm)

  const headerContent = useMemo(
    () => (
      <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
        <FlexItem>
          <ActivityNameField
            control={control}
            fieldId="sub-workflow-name"
            placeholder="Enter step name"
            ariaLabel="Name"
          />
        </FlexItem>
      </Flex>
    ),
    [control]
  )

  // Pattern shared across all node forms - pass header content to parent for builder UI
  // eslint-disable-next-line reactYouMightNotNeedAnEffect/no-pass-data-to-parent -- project-wide pattern, refactor all node forms together
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
    <Stack hasGutter>
      <StackItem>
        <WorkflowSelectionFields
          methods={methods}
          invocation={invocation}
          workflowId={workflowId}
          triggerNodeId={triggerNodeId}
          hasTriggers={triggers.length > 0}
          isVersionView={isVersionView}
        />
      </StackItem>
      {canConfigureInputMapping && !hasNoDeclaredInputs && (
        <StackItem>
          <WorkflowInputMapping
            methods={methods}
            inputFields={inputFields}
            sectionTitle={inputSectionTitle}
            freeformJson={freeformJson}
            isDisabled={isVersionView}
          />
        </StackItem>
      )}
    </Stack>
  )

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="sub-workflow-node-form" onSubmit={methods.handleSubmit(submitForm)}>
        <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={<SubWorkflowSettingsForm />} />
      </NodeFormContainer>
    </FormProvider>
  )
}
