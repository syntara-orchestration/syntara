import { Alert, Content, Stack, StackItem } from '@patternfly/react-core'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo } from 'react'
import { useFormContext } from 'react-hook-form'

import { ExpressionBuilderCore as ExpressionBuilder } from '../../../components/expressions/ExpressionBuilderCore'
import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { useSynForm } from '../../../hooks/useSynForm'
import { StepEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useStepEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { conditionFormSchema, type ConditionFormData } from './conditionFormSchema'
import { ActivityNameField } from './shared/ActivityNameField'
import { ConditionalExpressionHelp } from './shared/ConditionalExpressionHelp'
import { StepFormContainer } from './shared/StepFormContainer'
import stepFormStyles from './shared/stepFormStyles.module.css'
import { StepFormTabsLayout } from './shared/StepFormTabsLayout'

export type { ConditionFormData }

type ConditionStepFormProps = {
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
  const { control } = useFormContext<ConditionFormData>()

  const nameField = useMemo(
    () => <ActivityNameField control={control} fieldId="condition-name" ariaLabel="Name" />,
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
      {!onHeaderContentChange && <ActivityNameField fieldId="condition-name" />}

      <StackItem>
        <Alert
          variant="info"
          isExpandable
          isInline
          title="Only one branch runs per execution"
          className={stepFormStyles.compactAlert}
        >
          <Content component="p">
            The workflow follows the True branch when the expression matches, or the False branch otherwise. The other
            branch and its downstream steps are skipped.
          </Content>
        </Alert>
      </StackItem>

      <StackItem>
        <SynFormField
          name="condition"
          label="Condition type"
          labelHelp={<ConditionalExpressionHelp />}
          isRequired
          fieldId="condition-expression"
        >
          {({ field, fieldState }) => (
            <fieldset disabled={isVersionView} className={stepFormStyles.disabledFieldset}>
              <ExpressionBuilder
                id="condition-expression"
                value={typeof field.value === 'string' ? field.value : ''}
                onChange={field.onChange}
                error={!!fieldState.error}
                placeholder="Build your condition"
              />
            </fieldset>
          )}
        </SynFormField>
      </StackItem>
    </Stack>
  )

  return <StepFormTabsLayout parametersContent={parametersContent} hideSettingsTab />
}

export function ConditionStepForm(props: ConditionStepFormProps) {
  const defaultValues: ConditionFormData = {
    name: '',
    condition: '',
    ...props.initialData,
  }

  const form = useSynForm({
    schema: conditionFormSchema,
    defaultValues,
  })

  const autoSubmitRef = use(StepEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, props.onSubmit)

  return (
    <StepFormContainer formId="condition-step-form" onSubmit={form.handleSubmit(props.onSubmit)}>
      <SynForm form={form}>
        <ConditionFormFields onHeaderContentChange={props.onHeaderContentChange} />
      </SynForm>
    </StepFormContainer>
  )
}
