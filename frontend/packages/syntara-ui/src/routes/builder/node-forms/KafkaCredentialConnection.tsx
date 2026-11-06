import { Button, Content, Flex, Skeleton, Stack, StackItem } from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiWarningFillIcon } from '@patternfly/react-icons'
import { useCallback, useId, useState, type ReactElement, type ReactNode } from 'react'

import { FormFieldError } from '../../../components/FormFieldError'
import { IconLabel } from '../../../components/IconLabel'

import styles from './KafkaCredentialConnection.module.css'

/** Staged credential setup; configured credentials do not imply verified broker access. */
export function KafkaCredentialConnection({
  credentialName,
  isPending,
  errorMessage,
  isDisabled,
  isRequired = true,
  isCompact = false,
  credentialLabel = 'Kafka runtime credential',
  children,
}: Readonly<{
  credentialName?: string
  isPending: boolean
  errorMessage?: string
  isDisabled: boolean
  isRequired?: boolean
  isCompact?: boolean
  credentialLabel?: string
  children: (onSelected: () => void) => ReactNode
}>) {
  const [isPickerOpen, setIsPickerOpen] = useState(false)
  const errorId = useId()
  const [restoreFocus, setRestoreFocus] = useState(false)
  const actionRef = useCallback(
    (element: HTMLButtonElement | null) => {
      if (element && restoreFocus && !isPending) {
        element.focus()
        setRestoreFocus(false)
      }
    },
    [restoreFocus, isPending]
  )
  const configured = Boolean(credentialName && !errorMessage)
  const needsCredential = isRequired || Boolean(errorMessage)
  const missingCredentialText = `${credentialLabel} ${needsCredential ? 'not configured' : 'optional'}`
  let statusIcon: ReactElement | undefined
  if (configured) {
    statusIcon = <RhUiCheckCircleIcon className={styles.checkIcon} aria-hidden />
  } else if (needsCredential) {
    statusIcon = <RhUiWarningFillIcon className={styles.warningIcon} aria-hidden />
  }
  const closePicker = () => {
    setRestoreFocus(true)
    setIsPickerOpen(false)
  }

  const setupLabel = configured ? 'Change' : 'Set up connection'

  return (
    <Stack hasGutter={!isCompact} className={isCompact ? styles.compactStatusContainer : styles.statusContainer}>
      <StackItem>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          {isPending ? (
            <Skeleton screenreaderText="Loading Kafka runtime credential" />
          ) : (
            <IconLabel icon={statusIcon}>
              <Content component="small">{configured ? credentialName : missingCredentialText}</Content>
            </IconLabel>
          )}
          {!isDisabled && (
            <Button
              variant="link"
              size="sm"
              isDisabled={isPending}
              aria-describedby={!isPickerOpen && errorMessage ? errorId : undefined}
              ref={actionRef}
              onClick={() => (isPickerOpen ? closePicker() : setIsPickerOpen(true))}
            >
              {isPickerOpen ? 'Cancel' : setupLabel}
            </Button>
          )}
        </Flex>
      </StackItem>
      {!isPickerOpen && errorMessage && (
        <StackItem>
          <FormFieldError id={errorId} message={errorMessage} />
        </StackItem>
      )}
      {isPickerOpen && <StackItem>{children(closePicker)}</StackItem>}
    </Stack>
  )
}
