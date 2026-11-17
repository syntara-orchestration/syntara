import type { FormsAPI } from '@syntara/contracts'

import { resolveFormPromptCssOverride } from '../../../components/forms/resolveFormPromptCssOverride'
import { SynDynamicForm } from '../../../components/forms/SynDynamicForm'
import formStepResponseSurfaceStyles from '../../../components/forms/synFormStepResponseSurface.module.css'

type FormDefinition = FormsAPI.components['schemas']['FormDefinition']

type FormPromptPendingResponseFormProps = Readonly<{
  cssOverrideSource?: string | null
  responseFormId: string
  definition: FormDefinition
  submitLabel: string
  isDisabled: boolean
  isReadOnly: boolean
  disabledFieldTooltip?: string
  onSubmit: (responseData: Record<string, unknown>) => Promise<void>
}>

export function FormPromptPendingResponseForm({
  cssOverrideSource,
  responseFormId,
  definition,
  submitLabel,
  isDisabled,
  isReadOnly,
  disabledFieldTooltip,
  onSubmit,
}: FormPromptPendingResponseFormProps) {
  const cssOverride = resolveFormPromptCssOverride(cssOverrideSource)

  return (
    <div className={`${formStepResponseSurfaceStyles.formStepResponseForm} form-step-response-form`}>
      {cssOverride ? <style>{cssOverride}</style> : null}
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
