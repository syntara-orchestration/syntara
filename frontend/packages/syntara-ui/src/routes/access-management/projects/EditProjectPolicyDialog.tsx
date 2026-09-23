import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { z } from 'zod'

import { SynForm } from '../../../components/forms/SynForm'
import { useSynForm } from '../../../hooks/useSynForm'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import type { ProjectPolicyRead } from '../../access/types'

import { addProjectPolicySchema, policyStatementSchema } from './addProjectPolicySchema'
import type { AddProjectPolicyFormData } from './addProjectPolicySchema'
import { PolicyFormFields } from './PolicyFormFields'

type EditProjectPolicyDialogProps = {
  projectId: string
  policy?: ProjectPolicyRead
  onClose: () => void
  onSuccess: () => void
}

export function EditProjectPolicyDialog({
  projectId,
  policy,
  onClose,
  onSuccess,
}: Readonly<EditProjectPolicyDialogProps>) {
  const { showSuccess } = useAlerts()
  const mode = policy ? 'edit' : 'create'

  const form = useSynForm({
    schema: addProjectPolicySchema,
    defaultValues: {
      name: policy?.name ?? '',
      description: policy?.description ?? '',
      statementsJson: policy ? JSON.stringify(policy.statements ?? [], null, 2) : '[]',
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose, setValue, watch } = form
  const statementsJson = watch('statementsJson')

  const { mutate: updatePolicy, isPending } = accessClient.useMutation(
    'put',
    '/projects/{project_id}/policies/{policy_id}'
  )
  const { mutate: createPolicy, isPending: isCreating } = accessClient.useMutation(
    'post',
    '/projects/{project_id}/policies'
  )

  const onSubmit = (data: AddProjectPolicyFormData) => {
    const statements = z.array(policyStatementSchema).parse(JSON.parse(data.statementsJson))
    const body = {
      name: data.name,
      description: data.description || undefined,
      statements,
    }
    if (!policy) {
      createPolicy(
        {
          params: { path: { project_id: projectId } },
          body,
        },
        {
          onSuccess: () => {
            showSuccess({ title: 'Policy created', description: 'Policy created successfully' })
            handleClose()
            onSuccess()
          },
          onError: handleError({ title: 'Failed to create policy' }),
        }
      )
      return
    }
    updatePolicy(
      {
        params: { path: { project_id: projectId, policy_id: policy.id } },
        body,
      },
      {
        onSuccess: () => {
          showSuccess({ title: 'Policy updated', description: 'Policy updated successfully' })
          handleClose()
          onSuccess()
        },
        onError: handleError({ title: 'Failed to update policy' }),
      }
    )
  }

  const mutationIsPending = isPending || isCreating
  const formId = `${mode}-project-policy-form`

  return (
    <Modal isOpen onClose={handleClose} variant="medium">
      <ModalHeader title={mode === 'create' ? 'Create policy' : 'Edit Project Policy'} />
      <ModalBody>
        <Form id={formId} onSubmit={handleSubmit(onSubmit)}>
          <SynForm form={form}>
            <PolicyFormFields
              statementsJson={statementsJson}
              onAppendStatement={(next) =>
                setValue('statementsJson', next, { shouldDirty: true, shouldValidate: true })
              }
            />
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          form={formId}
          type="submit"
          isDisabled={mutationIsPending}
          isLoading={mutationIsPending}
        >
          {mode === 'create' ? 'Create' : 'Save policy'}
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={mutationIsPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
