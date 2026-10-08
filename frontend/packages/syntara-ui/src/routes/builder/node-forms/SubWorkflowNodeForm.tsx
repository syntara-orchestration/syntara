import { zodResolver } from '@hookform/resolvers/zod'
import { FormGroup, Stack, StackItem, TextInput } from '@patternfly/react-core'
import { use } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { z } from 'zod'

import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import type { BaseNodeFormProps } from '../registry/NodeRegistry'
import { useIsVersionView } from '../VersionViewContext'

import { NodeFormContainer } from './shared/NodeFormContainer'

/**
 * Form data for Sub-workflow step
 *
 * Note: This is a minimal form for palette registration (AAP-91268).
 * Configuration panel with target selector and input mapping will be
 * added in AAP-94089, AAP-94647, and AAP-94648.
 */
export type SubWorkflowFormData = {
  name: string
}

const subWorkflowFormSchema = z.object({
  name: z.string().trim().min(1, 'Step name is required'),
})

/**
 * Sub-workflow step configuration form
 *
 * AAP-91268: Palette registration only - minimal form with name field.
 * Full configuration (workflow selector, input mapping) is out of scope
 * and will be added in subsequent stories.
 */
export function SubWorkflowNodeForm({ onSubmit, initialData }: BaseNodeFormProps<SubWorkflowFormData>) {
  const isVersionView = useIsVersionView()

  const methods = useForm<SubWorkflowFormData>({
    resolver: zodResolver(subWorkflowFormSchema),
    defaultValues: {
      name: initialData?.name ?? '',
    },
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, onSubmit)

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="sub-workflow-node-form" onSubmit={methods.handleSubmit(onSubmit)}>
        <Stack hasGutter style={{ paddingInline: 'var(--pf-t--global--spacer--xs)' }}>
          <StackItem>
            <FormGroup label="Step name" isRequired>
              <TextInput
                id="sub-workflow-name"
                {...methods.register('name')}
                placeholder="Enter step name"
                type="text"
                aria-label="Step name"
                isDisabled={isVersionView}
              />
            </FormGroup>
          </StackItem>
        </Stack>
      </NodeFormContainer>
    </FormProvider>
  )
}
