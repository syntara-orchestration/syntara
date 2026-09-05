import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import type { ProjectPolicyRead } from '../../access/types'

import { addProjectPolicySchema, policyStatementSchema } from './addProjectPolicySchema'
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

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<AddProjectPolicyFormData>({
    resolver: zodResolver(addProjectPolicySchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: policy.name,
      description: policy.description ?? '',
      statementsJson: JSON.stringify(policy.statements ?? [], null, 2),
    },
  })

  const handleError = useFormMutationErrorHandler<AddProjectPolicyFormData>(setError)
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
          onSuccess()
          onClose()
        },
        onError: handleError({ title: 'Failed to update policy' }),
      }
    )
  }

  return (
    <Modal isOpen onClose={onClose} variant="medium">
      <ModalHeader title="Edit Project Policy" />
      <ModalBody>
        <Form id="edit-project-policy-form" onSubmit={handleSubmit(onSubmit)}>
          <FormGroup label="Name" isRequired fieldId="project-policy-name">
            <TextInput
              id="project-policy-name"
              isRequired
              aria-label="Policy name"
              validated={errors.name ? 'error' : 'default'}
              {...register('name')}
            />
            {errors.name ? (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem variant="error">{errors.name.message}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            ) : (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>Lowercase alphanumeric with hyphens (e.g. my-custom-policy)</HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>

          <FormGroup label="Description" fieldId="project-policy-description">
            <TextInput
              id="project-policy-description"
              aria-label="Policy description"
              validated={errors.description ? 'error' : 'default'}
              {...register('description')}
            />
            {errors.description && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem variant="error">{errors.description.message}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>

          <FormGroup label="Statements" isRequired fieldId="project-policy-statements">
            <TextArea
              id="project-policy-statements"
              aria-label="Policy statements JSON"
              validated={errors.statementsJson ? 'error' : 'default'}
              rows={10}
              resizeOrientation="vertical"
              {...register('statementsJson')}
            />
            {errors.statementsJson ? (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem variant="error">{errors.statementsJson.message}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            ) : (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>
                    JSON array of statement objects with effect, actions, and scope fields
                  </HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" form="edit-project-policy-form" type="submit" isLoading={isPending}>
          Save policy
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
