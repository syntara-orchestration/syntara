import { FormTriggerRunDialog } from '../../workflows/formTrigger/FormTriggerRunDialog'
import type { FormTriggerPresentation } from '../../workflows/formTrigger/formTriggerRunUtils'

import { RunWorkflowModal } from './RunWorkflowModal'

type BuilderRunInputStepProps = Readonly<{
  showInputStep: boolean
  showFormTriggerDialog: boolean
  formTrigger?: FormTriggerPresentation
  workflowId: string | null
  triggerNodeId?: string
  workflowName: string
  triggerName: string
  triggerInputSchema?: Record<string, unknown>
  canRun: boolean
  runTooltip: string
  onClose: () => void
  onRunWorkflow: (inputData?: Record<string, unknown>, triggerNodeId?: string) => void
}>

export function BuilderRunInputStep({
  showInputStep,
  showFormTriggerDialog,
  formTrigger,
  workflowId,
  triggerNodeId,
  workflowName,
  triggerName,
  triggerInputSchema,
  canRun,
  runTooltip,
  onClose,
  onRunWorkflow,
}: BuilderRunInputStepProps) {
  if (showInputStep && showFormTriggerDialog && formTrigger && workflowId && triggerNodeId) {
    return (
      <FormTriggerRunDialog
        key={`form-${triggerNodeId}`}
        isOpen
        onClose={onClose}
        workflowId={workflowId}
        workflowName={workflowName}
        triggerNodeId={triggerNodeId}
        triggerName={triggerName}
        formTrigger={formTrigger}
        canRun={canRun}
        runTooltip={runTooltip}
      />
    )
  }

  return (
    <RunWorkflowModal
      key={showInputStep ? `open-${triggerNodeId ?? ''}` : 'closed'}
      isOpen={showInputStep}
      onClose={onClose}
      onConfirm={onRunWorkflow}
      workflowName={workflowName}
      triggerName={triggerName}
      triggerNodeId={triggerNodeId}
      inputSchema={triggerInputSchema}
      workflowId={workflowId}
    />
  )
}
