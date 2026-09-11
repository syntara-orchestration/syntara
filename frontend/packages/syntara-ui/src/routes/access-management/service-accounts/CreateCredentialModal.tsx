import { Button, Content, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useCallback } from 'react'

import { useBlurOnOpen } from '../../../hooks/useBlurOnOpen'

import styles from './CreateCredentialModal.module.css'
import { CredentialExpirationField } from './CredentialExpirationField'
import { useCredentialExpirationDate } from './useCredentialExpirationDate'

type CreateCredentialModalProps = {
  isOpen: boolean
  onClose: () => void
  onSubmit: (expiresAt: string) => void
  isPending: boolean
  maxLifetimeDays?: number
}

function CreateCredentialForm({
  onClose,
  onSubmit,
  isPending,
  maxLifetimeDays,
}: Readonly<Omit<CreateCredentialModalProps, 'isOpen'>>) {
  const { value, error, handleChange, validator, helperText } = useCredentialExpirationDate(maxLifetimeDays)

  const handleSubmit = useCallback(() => {
    if (error) return
    onSubmit(`${value}T00:00:00Z`)
  }, [value, error, onSubmit])

  return (
    <>
      <ModalBody>
        <Form id="create-credential-form" onSubmit={(e) => e.preventDefault()}>
          <CredentialExpirationField
            selectedDate={value}
            onDateChange={handleChange}
            dateError={error}
            validator={validator}
            helperText={helperText}
          />
          <Content component="p" className={styles.description}>
            A new client ID and client secret will be generated. The secret is shown only once after creation.
          </Content>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={handleSubmit}
          isDisabled={isPending || !!error}
          isLoading={isPending}
          icon={<RhUiAddIcon />}
        >
          Create credential
        </Button>
        <Button variant="link" onClick={onClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </>
  )
}

export function CreateCredentialModal({
  isOpen,
  onClose,
  onSubmit,
  isPending,
  maxLifetimeDays,
}: Readonly<CreateCredentialModalProps>) {
  useBlurOnOpen(isOpen)
  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="small">
      <ModalHeader title="Create credential" />
      {isOpen && (
        <CreateCredentialForm
          onClose={onClose}
          onSubmit={onSubmit}
          isPending={isPending}
          maxLifetimeDays={maxLifetimeDays}
        />
      )}
    </Modal>
  )
}
