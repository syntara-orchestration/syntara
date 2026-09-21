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

type EditProjectPolicyDialogProps = {
  projectId: string
  policy: ProjectPolicyRead
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

  const form = useSynForm({
    schema: addProjectPolicySchema,
    defaultValues: {
      name: policy.name,
      description: policy.description ?? '',
      statementsJson: JSON.stringify(policy.statements ?? [], null, 2),
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose } = form

  const { mutate: updatePolicy, isPending } = accessClient.useMutation(
    'put',
    '/projects/{project_id}/policies/{policy_id}'
  )

  const onSubmit = (data: AddProjectPolicyFormData) => {
    const statements = z.array(policyStatementSchema).parse(JSON.parse(data.statementsJson))
    updatePolicy(
      {
        params: { path: { project_id: projectId, policy_id: policy.id } },
        body: {
          name: data.name,
          description: data.description || undefined,
          statements,
        },
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

  return (
    <Modal isOpen onClose={handleClose} variant="medium">
      <ModalHeader title="Edit Project Policy" />
      <ModalBody>
        <Form id="edit-project-policy-form" onSubmit={handleSubmit(onSubmit)}>
          <SynForm form={form}>
            <SynTextField
              name="name"
              label="Policy name"
              fieldId="project-policy-name"
              isRequired
              hint={PROJECT_POLICY_NAME_HINT}
            />
            <SynTextField name="description" label="Policy description" fieldId="project-policy-description" />
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
          form="edit-project-policy-form"
          type="submit"
          isDisabled={isPending}
          isLoading={isPending}
        >
          Save policy
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
