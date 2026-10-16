import { zodResolver } from '@hookform/resolvers/zod'
import { Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import { type ReactNode, use, useEffect, useMemo } from 'react'
import { Controller, FormProvider, useForm } from 'react-hook-form'
import { z } from 'zod'

import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import type { BaseNodeFormProps } from '../registry/NodeRegistry'
import { useIsVersionView } from '../VersionViewContext'

import { ChildWorkflowSelector } from './ChildWorkflowSelector'
import { InputMappingFields, type InputMappingEntry } from './InputMappingFields'
import { ActivityNameField } from './shared/ActivityNameField'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { nodeSettingsSchema } from './shared/nodeSettingsSchema'
import { SubWorkflowSettingsForm } from './SubWorkflowSettingsForm'

/**
 * Form data for Sub-workflow step configuration
 */
export type SubWorkflowFormData = {
  name: string
  workflow_id: string | null
  input_mapping: InputMappingEntry[]
  settings?: z.infer<typeof nodeSettingsSchema> & { expected_duration?: number }
}

const subWorkflowSettingsSchema = nodeSettingsSchema.extend({
  expected_duration: z.number().int().positive().optional(),
})

const subWorkflowFormSchema = z.object({
  name: z.string().trim().min(1, 'Step name is required'),
  workflow_id: z.string().nullable(),
  input_mapping: z.array(
    z.object({
      id: z.string(),
      key: z.string(),
      value: z.string(),
    })
  ),
  settings: subWorkflowSettingsSchema.optional(),
})

/**
 * Sub-workflow step configuration form
 *
 * Allows user to:
 * - Name the step
 * - Select a child workflow
 * - Configure input mappings
 */
export function SubWorkflowNodeForm({
  onSubmit,
  initialData,
  onHeaderContentChange,
  projectId,
}: BaseNodeFormProps<SubWorkflowFormData>) {
  const isVersionView = useIsVersionView()

  console.log('[SubWorkflowNodeForm] Project from props:', { projectId })

  const methods = useForm<SubWorkflowFormData>({
    resolver: zodResolver(subWorkflowFormSchema),
    defaultValues: {
      name: initialData?.name ?? '',
      workflow_id: initialData?.workflow_id ?? null,
      input_mapping: initialData?.input_mapping ?? [],
      settings: initialData?.settings ?? {},
    },
  })

  const { control } = methods
  const workflowId = methods.watch('workflow_id')

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, onSubmit)

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
    <Stack hasGutter style={{ paddingInline: 'var(--pf-t--global--spacer--xs)' }}>
      <StackItem>
        <Controller
          name="workflow_id"
          control={methods.control}
          render={({ field }) => (
            <ChildWorkflowSelector
              projectId={projectId ?? null}
              selectedWorkflowId={field.value}
              onChange={field.onChange}
              labelHelp={nodeHelp.subworkflowWorkflow}
              isRequired
              isDisabled={isVersionView}
            />
          )}
        />
      </StackItem>

      <StackItem>
        <Controller
          name="input_mapping"
          control={methods.control}
          render={({ field }) => (
            <InputMappingFields
              entries={field.value}
              onChange={field.onChange}
              isDisabled={isVersionView || !workflowId}
            />
          )}
        />
      </StackItem>
    </Stack>
  )

  const settingsContent = <SubWorkflowSettingsForm />

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="sub-workflow-node-form" onSubmit={methods.handleSubmit(onSubmit)}>
        <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
      </NodeFormContainer>
    </FormProvider>
  )
}
