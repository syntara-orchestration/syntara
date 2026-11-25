import { Button, Content, Flex, FlexItem, Skeleton, Stack, StackItem } from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiWarningFillIcon } from '@patternfly/react-icons'
import { useCallback, useId, useState, type ReactElement, type ReactNode } from 'react'

import { FormFieldError } from '../../../components/FormFieldError'
import { IconLabel } from '../../../components/IconLabel'

import styles from './KafkaCredentialConnection.module.css'

function CredentialStatus({
  isPending,
  configured,
  isClientIdentity,
  needsCredential,
  credentialName,
  credentialLabel,
}: Readonly<{
  isPending: boolean
  configured: boolean
  isClientIdentity?: boolean
  needsCredential: boolean
  credentialName?: string
  credentialLabel: string
}>) {
  if (isPending) return <Skeleton fontSize="sm" screenreaderText="Loading Kafka runtime credential" />

  const missingCredentialText = `${credentialLabel} ${needsCredential ? 'not configured' : 'optional'}`
  const label = configured || isClientIdentity ? (credentialName ?? missingCredentialText) : missingCredentialText
  let icon: ReactElement | undefined
  if (configured) {
    icon = <RhUiCheckCircleIcon className={styles.checkIcon} aria-hidden />
  } else if (needsCredential) {
    icon = <RhUiWarningFillIcon className={styles.warningIcon} aria-hidden />
  }
  return (
    <IconLabel icon={icon}>
      <Content component="small">{label}</Content>
    </IconLabel>
  )
}

type KafkaCredentialConnectionProps = Readonly<{
  credentialName?: string
  isClientIdentity?: boolean
  isPending: boolean
  errorMessage?: string
  tlsMode?: string
  isDisabled: boolean
  isRequired?: boolean
  isCompact?: boolean
  credentialLabel?: string
  children: (onSelected: () => void) => ReactNode
}>

/** Compact credential setup; configured credentials do not imply verified broker access. */
export function KafkaCredentialConnection({
  credentialName,
  isClientIdentity = false,
  isPending,
  errorMessage,
  tlsMode,
  isDisabled,
  isRequired = true,
  isCompact = false,
  credentialLabel = 'Kafka runtime credential',
  children,
}: KafkaCredentialConnectionProps) {
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
  const visibleError = isPending ? undefined : errorMessage
  const configured = Boolean(credentialName && !visibleError)
  const closePicker = () => {
    setRestoreFocus(true)
    setIsPickerOpen(false)
  }

  const setupLabel = configured ? 'Change' : 'Set up connection'

  return (
    <Stack hasGutter={!isCompact} className={isCompact ? styles.compactStatusContainer : styles.statusContainer}>
      <StackItem>
        <Flex
          className={styles.statusRow}
          justifyContent={{ default: 'justifyContentSpaceBetween' }}
          alignItems={{ default: 'alignItemsCenter' }}
          flexWrap={{ default: 'nowrap' }}
        >
          <FlexItem grow={{ default: 'grow' }} className={styles.statusLabel}>
            <CredentialStatus
              isPending={isPending}
              configured={configured}
              isClientIdentity={isClientIdentity}
              needsCredential={isRequired || Boolean(visibleError)}
              credentialName={credentialName}
              credentialLabel={credentialLabel}
            />
          </FlexItem>
          {!isDisabled && (
            <FlexItem flex={{ default: 'flexNone' }}>
              <Button
                variant="link"
                size="sm"
                isDisabled={isPending}
                aria-describedby={!isPickerOpen && visibleError ? errorId : undefined}
                ref={actionRef}
                onClick={() => (isPickerOpen ? closePicker() : setIsPickerOpen(true))}
              >
                {isPickerOpen ? 'Cancel' : setupLabel}
              </Button>
            </FlexItem>
          )}
        </Flex>
      </StackItem>
      {configured && tlsMode && (
        <StackItem>
          <Content component="small">{tlsMode}</Content>
        </StackItem>
      )}
      {!isPickerOpen && visibleError && (
        <StackItem>
          <FormFieldError id={errorId} message={visibleError} />
        </StackItem>
      )}
      {isPickerOpen && <StackItem>{children(closePicker)}</StackItem>}
    </Stack>
  )
}
