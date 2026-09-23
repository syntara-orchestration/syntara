import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { z } from 'zod'

import { SynForm } from '../../../components/forms/SynForm'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import type { ProjectPolicyRead } from '../../access/types'

import {
  addProjectPolicySchema,
  policyStatementSchema,
  PROJECT_POLICY_NAME_HINT,
  STATEMENTS_JSON_HINT,
} from './addProjectPolicySchema'
import type { AddProjectPolicyFormData } from './addProjectPolicySchema'
import { NodeKindStatementBuilder } from './NodeKindStatementBuilder'

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
            <SynTextField
              name="name"
              label="Policy name"
              fieldId="project-policy-name"
              isRequired
              hint={PROJECT_POLICY_NAME_HINT}
            />
            <SynTextField name="description" label="Policy description" fieldId="project-policy-description" />
            <NodeKindStatementBuilder
              statementsJson={statementsJson}
              onAppend={(next) => setValue('statementsJson', next, { shouldDirty: true, shouldValidate: true })}
            />
            <SynTextAreaField
              name="statementsJson"
              label="Policy statements JSON"
              fieldId="project-policy-statements"
              isRequired
              hint={STATEMENTS_JSON_HINT}
              rows={10}
              resizeOrientation="vertical"
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
