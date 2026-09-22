import { Alert, Content, DescriptionList, Stack, StackItem } from '@patternfly/react-core'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo } from 'react'
import { FormProvider, useForm, useFormContext } from 'react-hook-form'

import { SynDetail } from '../../../components/details/SynDetail'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'

import { permissionCheckFormSchema, type PermissionCheckFormData } from './permissionCheckFormSchema'
import { ActivityNameField } from './shared/ActivityNameField'
import { zodResolver } from './shared/formSchemaUtils'
import { NodeFormContainer } from './shared/NodeFormContainer'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'

export type { PermissionCheckFormData }

type PermissionCheckNodeFormProps = {
  onSubmit: (data: PermissionCheckFormData) => void
  initialData?: Partial<PermissionCheckFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}

function PermissionCheckFormFields({
  onHeaderContentChange,
}: Readonly<{ onHeaderContentChange?: (content: ReactNode | null) => void }>) {
  const { register } = useFormContext<PermissionCheckFormData>()

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="permission-check-name" ariaLabel="Name" />,
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
      {!onHeaderContentChange && <ActivityNameField register={register} fieldId="permission-check-name" />}

      <StackItem>
        <Alert variant="info" isInline title="This step has no configuration" className={nodeFormStyles.compactAlert}>
          <Content component="p">
            The permission check always evaluates the single step connected to its input. When that step was not allowed
            to run for this execution, the workflow follows the Denied branch; otherwise it follows the Allowed branch.
          </Content>
        </Alert>
      </StackItem>

      <StackItem>
        <DescriptionList isHorizontal isCompact>
          <SynDetail label="Input">Exactly one incoming connection — the step being checked.</SynDetail>
          <SynDetail label="Allowed branch">Taken when the checked step was permitted to run.</SynDetail>
          <SynDetail label="Denied branch">Taken when a policy denied the checked step for this run.</SynDetail>
        </DescriptionList>
      </StackItem>
    </Stack>
  )

  return <NodeFormTabsLayout parametersContent={parametersContent} hideSettingsTab />
}

export function PermissionCheckNodeForm(props: Readonly<PermissionCheckNodeFormProps>) {
  const defaultValues: PermissionCheckFormData = {
    name: '',
    ...props.initialData,
  }

  const methods = useForm<PermissionCheckFormData>({
    resolver: zodResolver(permissionCheckFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, props.onSubmit)

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="permission-check-node-form" onSubmit={methods.handleSubmit(props.onSubmit)}>
        <PermissionCheckFormFields onHeaderContentChange={props.onHeaderContentChange} />
      </NodeFormContainer>
    </FormProvider>
  )
}
