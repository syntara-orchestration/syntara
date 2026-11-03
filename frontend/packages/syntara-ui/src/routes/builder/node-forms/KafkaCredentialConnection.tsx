import { Button, Content, Flex, Skeleton, Stack, StackItem } from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiWarningFillIcon } from '@patternfly/react-icons'
import { useCallback, useId, useState, type ReactNode } from 'react'

import { FormFieldError } from '../../../components/FormFieldError'
import { IconLabel } from '../../../components/IconLabel'

import styles from './KafkaCredentialConnection.module.css'

/** Staged credential setup; configured credentials do not imply verified broker access. */
export function KafkaCredentialConnection({
  credentialName,
  isPending,
  errorMessage,
  isDisabled,
  children,
}: Readonly<{
  credentialName?: string
  isPending: boolean
  errorMessage?: string
  isDisabled: boolean
  children: (onSelected: () => void) => ReactNode
}>) {
  const [isPickerOpen, setIsPickerOpen] = useState(false)
  const errorId = useId()
  const [restoreFocus, setRestoreFocus] = useState(false)
  const actionRef = useCallback(
    (element: HTMLButtonElement | null) => {
      if (element && restoreFocus) {
        element.focus()
        setRestoreFocus(false)
      }
    },
    [restoreFocus]
  )
  const configured = Boolean(credentialName && !errorMessage)
  const closePicker = () => {
    setRestoreFocus(true)
    setIsPickerOpen(false)
  }

  const setupLabel = configured ? 'Change' : 'Set up connection'

  return (
    <Stack hasGutter className={styles.statusContainer}>
      <StackItem>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          {isPending ? (
            <Skeleton screenreaderText="Loading Kafka runtime credential" />
          ) : (
            <IconLabel
              icon={
                configured ? (
                  <RhUiCheckCircleIcon className={styles.checkIcon} aria-hidden />
                ) : (
                  <RhUiWarningFillIcon className={styles.warningIcon} aria-hidden />
                )
              }
            >
              <Content component="small">
                {configured ? credentialName : 'Kafka runtime credential not configured'}
              </Content>
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
