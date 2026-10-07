import {
  Alert,
  Content,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo } from 'react'
import { Controller, FormProvider, useForm, useFormContext } from 'react-hook-form'

import { ExpressionBuilderCore as ExpressionBuilder } from '../../../components/expressions/ExpressionBuilderCore'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { conditionFormSchema, type ConditionFormData } from './conditionFormSchema'
import { ActivityNameField } from './shared/ActivityNameField'
import { ConditionalExpressionHelp } from './shared/ConditionalExpressionHelp'
import { zodResolver } from './shared/formSchemaUtils'
import { NodeFormContainer } from './shared/NodeFormContainer'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'

export type { ConditionFormData }

type ConditionNodeFormProps = {
  onSubmit: (data: ConditionFormData) => void
  initialData?: Partial<ConditionFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}

function ConditionFormFields({
  onHeaderContentChange,
}: {
  onHeaderContentChange?: (content: ReactNode | null) => void
}) {
  const isVersionView = useIsVersionView()
  const { register, control } = useFormContext<ConditionFormData>()

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="condition-name" ariaLabel="Name" />,
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
      {!onHeaderContentChange && <ActivityNameField register={register} fieldId="condition-name" />}

      <StackItem>
        <Alert
          variant="info"
          isExpandable
          isInline
          title="Only one branch runs per execution"
          className={nodeFormStyles.compactAlert}
        >
          <Content component="p">
            The workflow follows the True branch when the expression matches, or the False branch otherwise. The other
            branch and its downstream steps are skipped.
          </Content>
        </Alert>
      </StackItem>

      <StackItem>
        <FormGroup
          label="Condition type"
          labelHelp={<ConditionalExpressionHelp />}
          isRequired
          fieldId="condition-expression"
        >
          <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
            <Controller
              control={control}
              name="condition"
              render={({ field, fieldState }) => (
                <>
                  <ExpressionBuilder
                    id="condition-expression"
                    value={field.value || ''}
                    onChange={field.onChange}
                    error={!!fieldState.error}
                    placeholder="Build your condition"
                  />
                  {fieldState.error && (
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem variant="error">{fieldState.error.message}</HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  )}
                </>
              )}
            />
          </fieldset>
        </FormGroup>
      </StackItem>
    </Stack>
  )

  return <NodeFormTabsLayout parametersContent={parametersContent} hideSettingsTab />
}

export function ConditionNodeForm(props: ConditionNodeFormProps) {
  const defaultValues: ConditionFormData = {
    name: '',
    condition: '',
    ...props.initialData,
  }

  const methods = useForm<ConditionFormData>({
    resolver: zodResolver(conditionFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, props.onSubmit)

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="condition-node-form" onSubmit={methods.handleSubmit(props.onSubmit)}>
        <ConditionFormFields onHeaderContentChange={props.onHeaderContentChange} />
      </NodeFormContainer>
    </FormProvider>
  )
}
