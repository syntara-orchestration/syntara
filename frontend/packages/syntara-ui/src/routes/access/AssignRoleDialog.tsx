import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'

import { AssignRoleFormBody } from './AssignRoleFormBody'
import { useAssignRoleDialog } from './useAssignRoleDialog'

type AssignRoleDialogProps = {
  onClose: () => void
  onSuccess: () => void
}

export function AssignRoleDialog({ onClose, onSuccess }: Readonly<AssignRoleDialogProps>) {
  const { handleSubmit, onSubmit, handleClose, isPending, formBodyProps } = useAssignRoleDialog({
    onClose,
    onSuccess,
  })

  return (
    <Modal isOpen onClose={handleClose} variant="small">
      <ModalHeader title="Add Assignment" />
      <ModalBody>
        <Form id="assign-role-form" onSubmit={handleSubmit(onSubmit)}>
          <AssignRoleFormBody {...formBodyProps} />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          form="assign-role-form"
          type="submit"
          isDisabled={isPending}
          isLoading={isPending}
          icon={<RhUiAddIcon />}
        >
          Add assignment
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
