import type { FormsAPI } from '@syntara/contracts'

import { SynDynamicForm } from '../../../components/forms/SynDynamicForm'
import formStepResponseSurfaceStyles from '../../../components/forms/synFormStepResponseSurface.module.css'

type FormDefinition = FormsAPI.components['schemas']['FormDefinition']

type FormPromptPendingResponseFormProps = Readonly<{
  responseFormId: string
  definition: FormDefinition
  submitLabel: string
  isDisabled: boolean
  isReadOnly: boolean
  disabledFieldTooltip?: string
  onSubmit: (responseData: Record<string, unknown>) => Promise<void>
}>

export function FormPromptPendingResponseForm({
  responseFormId,
  definition,
  submitLabel,
  isDisabled,
  isReadOnly,
  disabledFieldTooltip,
  onSubmit,
}: FormPromptPendingResponseFormProps) {
  return (
    <div className={`${formStepResponseSurfaceStyles.formStepResponseForm} form-step-response-form`}>
      <SynDynamicForm
        id={responseFormId}
        definition={definition}
        submitLabel={submitLabel}
        isDisabled={isDisabled}
        isReadOnly={isReadOnly}
        disabledFieldTooltip={disabledFieldTooltip}
        hideSubmitButton
        textAreaControlClassName={formStepResponseSurfaceStyles.formStepResponseTextAreaControl}
        onSubmit={onSubmit}
      />
    </div>
  )
}
