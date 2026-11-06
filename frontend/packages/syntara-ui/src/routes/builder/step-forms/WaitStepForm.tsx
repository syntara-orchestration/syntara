import { Stack, StackItem } from '@patternfly/react-core'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo } from 'react'
import { useFormContext } from 'react-hook-form'

import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { useSynForm } from '../../../hooks/useSynForm'
import { StepEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useStepEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { ActivityNameField } from './shared/ActivityNameField'
import { DurationInput } from './shared/DurationInput'
import { stepHelp } from './shared/stepFieldHelp'
import { StepFormContainer } from './shared/StepFormContainer'
import { StepFormTabsLayout } from './shared/StepFormTabsLayout'
import { StepSettingsForm } from './shared/StepSettingsForm'
import { useMaxWaitDuration } from './useMaxWaitDuration'
import { createWaitFormSchema, type WaitFormData } from './waitFormSchema'

export type { WaitFormData }

type WaitStepFormProps = {
  onSubmit: (data: WaitFormData) => void
  initialData?: Partial<WaitFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}

type WaitFormFieldsProps = Readonly<{
  onHeaderContentChange?: (content: ReactNode | null) => void
}>

function WaitFormFields({ onHeaderContentChange }: WaitFormFieldsProps) {
  const isVersionView = useIsVersionView()
  const { control } = useFormContext<WaitFormData>()

  const nameField = useMemo(
    () => <ActivityNameField control={control} fieldId="wait-name" ariaLabel="Name" />,
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
      {!onHeaderContentChange && <ActivityNameField fieldId="wait-name" />}

      <StackItem>
        <SynFormField
          name="duration"
          label="Wait duration"
          labelHelp={stepHelp.waitDuration}
          fieldId="wait-duration"
          isRequired
        >
          {({ field, fieldState }) => (
            <DurationInput
              value={field.value as number | undefined}
              onChange={field.onChange}
              idPrefix="wait"
              isDisabled={isVersionView}
              validated={fieldState.error ? 'error' : undefined}
            />
          )}
        </SynFormField>
      </StackItem>
    </Stack>
  )

  const settingsContent = <StepSettingsForm supportsTimeout={false} supportsRetryPolicy={false} />

  return <StepFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function WaitStepForm(props: Readonly<WaitStepFormProps>) {
  const { maxSeconds, isLoading } = useMaxWaitDuration()

  const schema = useMemo(() => createWaitFormSchema(maxSeconds), [maxSeconds])

  const defaultValues: WaitFormData = {
    name: '',
    settings: {},
    duration: undefined,
    ...props.initialData,
  }

  const form = useSynForm({
    schema,
    defaultValues,
    mode: 'onChange',
  })

  const autoSubmitRef = use(StepEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, props.onSubmit)

  if (isLoading) return null

  return (
    <StepFormContainer formId="wait-step-form" onSubmit={form.handleSubmit(props.onSubmit)}>
      <SynForm form={form}>
        <WaitFormFields onHeaderContentChange={props.onHeaderContentChange} />
      </SynForm>
    </StepFormContainer>
  )
}
