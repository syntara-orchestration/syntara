import { Alert, Button, Modal, ModalBody, ModalFooter, ModalHeader, Stack, StackItem } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo, useState } from 'react'

import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { SynDynamicForm } from '../../../components/forms/SynDynamicForm'
import { FormDataValidationError } from '../../../forms'
import { useBlurOnOpen } from '../../../hooks/useBlurOnOpen'
import { useAlerts } from '../../../providers/alerts'
import { detachPromise } from '../../../utils/detachPromise'
import { resolveFormPromptCssOverride } from '../../executions/formPrompt/resolveFormPromptCssOverride'
import styles from '../../executions/FormPromptResponseContent.module.css'

import type { FormTriggerPresentation } from './formTriggerRunUtils'
import { submitFormTriggerExecution } from './submitFormTriggerExecution'

type FormTriggerRunDialogProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  workflowId: string
  workflowName: string
  triggerNodeId: string
  triggerName: string
  formTrigger: FormTriggerPresentation
  usePublished?: boolean
  canRun: boolean
  runTooltip: string
  isCheckingPermissions?: boolean
}>

export function FormTriggerRunDialog({
  isOpen,
  onClose,
  workflowId,
  workflowName,
  triggerNodeId,
  triggerName,
  formTrigger,
  usePublished = false,
  canRun,
  runTooltip,
  isCheckingPermissions = false,
}: FormTriggerRunDialogProps) {
  useBlurOnOpen(isOpen)
  const navigate = useNavigate()
  const { showSuccess } = useAlerts()
  const [submitFailed, setSubmitFailed] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const cssOverride = useMemo(() => resolveFormPromptCssOverride(formTrigger.cssOverride), [formTrigger.cssOverride])
  const message = formTrigger.message?.trim() || undefined
  const submitLabel = formTrigger.submitLabel?.trim() || 'Submit'
  const successMessage = formTrigger.successMessage?.trim() || 'Your request was submitted.'
  const formId = `form-trigger-run-${triggerNodeId}`

  const handleClose = useCallback(() => {
    setSubmitFailed(false)
    onClose()
  }, [onClose])

  const handleSubmit = useCallback(
    async (inputData: Record<string, unknown>) => {
      setSubmitFailed(false)
      setIsSubmitting(true)
      try {
        const executionId = await submitFormTriggerExecution({
          workflowId,
          triggerNodeId,
          inputData,
          usePublished,
          formDefinition: formTrigger.definition,
        })
        showSuccess({ title: 'Submission successful', description: successMessage })
        onClose()
        detachPromise(
          navigate({
            to: '/executions/$executionId',
            params: { executionId },
            search: { history: 'closed' },
          })
        )
      } catch (error) {
        if (error instanceof FormDataValidationError) {
          throw error
        }
        setSubmitFailed(true)
      } finally {
        setIsSubmitting(false)
      }
    },
    [formTrigger.definition, navigate, onClose, showSuccess, successMessage, triggerNodeId, usePublished, workflowId]
  )

  const mayRun = canRun && !isCheckingPermissions
  const formBusy = isSubmitting || isCheckingPermissions
  const submitDisabled = !mayRun || isSubmitting
  const permissionTooltip = mayRun || isCheckingPermissions ? undefined : runTooltip

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium" aria-label={`Run ${triggerName} form`}>
      <ModalHeader
        title={`Run ${workflowName}`}
        description={`Complete the form for ${triggerName} to start this workflow.`}
      />
      <ModalBody>
        {submitFailed ? (
          <Alert variant="danger" isInline title="Submission failed" className="pf-v6-u-mb-md">
            Unable to submit this form. Try again or contact your administrator.
          </Alert>
        ) : null}
        <Stack hasGutter>
          <StackItem>
            <div className={`${styles.formStepResponseForm} form-step-response-form`}>
              {cssOverride ? <style>{cssOverride}</style> : null}
              <SynDynamicForm
                id={formId}
                data-testid="form-trigger-run-form"
                definition={formTrigger.definition}
                description={message}
                submitLabel={submitLabel}
                isDisabled={!mayRun}
                isLoading={formBusy}
                disabledFieldTooltip={permissionTooltip}
                hideSubmitButton
                textAreaControlClassName={styles.formStepResponseTextAreaControl}
                onSubmit={handleSubmit}
                onValidationError={() => setSubmitFailed(false)}
              />
            </div>
          </StackItem>
        </Stack>
      </ModalBody>
      <ModalFooter>
        <DisabledWithTooltip isDisabled={!mayRun && !isCheckingPermissions} content={runTooltip}>
          <Button type="submit" form={formId} variant="primary" isDisabled={submitDisabled} isLoading={formBusy}>
            {submitLabel}
          </Button>
        </DisabledWithTooltip>
        <Button variant="link" onClick={handleClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
