import type { FormDefinition } from '@syntara/contracts'

import { SynDynamicForm } from './SynDynamicForm'
import formStepResponseSurfaceStyles from './synFormStepResponseSurface.module.css'

type SynFormDefinitionPreviewProps = Readonly<{
  definition: FormDefinition
  description?: string | null
  submitLabel?: string | null
}>

/** Read-only preview of a workflow form definition (builder / modal). */
export function SynFormDefinitionPreview({ definition, description, submitLabel }: SynFormDefinitionPreviewProps) {
  const resolvedSubmitLabel = submitLabel?.trim() || 'Submit'
  const trimmedDescription = description?.trim()

  return (
    <div className={`${formStepResponseSurfaceStyles.formStepResponseForm} form-step-response-form`}>
      <SynDynamicForm
        definition={definition}
        description={trimmedDescription || undefined}
        submitLabel={resolvedSubmitLabel}
        isReadOnly
        showSubmitWhenReadOnly
        textAreaControlClassName={formStepResponseSurfaceStyles.formStepResponseTextAreaControl}
        onSubmit={() => undefined}
      />
    </div>
  )
}
