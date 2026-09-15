import { Alert, AlertActionCloseButton, AlertGroup } from '@patternfly/react-core'
import { useId, useState, useCallback, useRef, useMemo, type ReactNode } from 'react'

import { AlertContext, type AlertConfig, type AlertMessage, type AlertVariant } from './AlertContext'
import './AlertProvider.css'

type AlertItem = {
  /** Stable key for React list + dismiss; optional consumer `config.id` or monotonic instance id */
  instanceKey: string
  variant: AlertVariant
} & Omit<AlertConfig, 'variant' | 'id'>

const DEFAULT_TIMEOUT = 8000

type ToastAlertItemProps = Readonly<{
  alert: AlertItem
  onDismiss: (instanceKey: string) => void
}>

function ToastAlertItem({ alert, onDismiss }: ToastAlertItemProps) {
  const alertDomId = `syntara-alert-${useId()}`

  return (
    <Alert
      id={alertDomId}
      variant={alert.variant}
      title={alert.title}
      timeout={alert.autoDismiss ? (alert.timeout ?? DEFAULT_TIMEOUT) : undefined}
      onTimeout={() => onDismiss(alert.instanceKey)}
      actionClose={<AlertActionCloseButton onClose={() => onDismiss(alert.instanceKey)} />}
      actionLinks={alert.actionLinks}
    >
      {alert.description}
    </Alert>
  )
}

export function AlertProvider({ children }: { children: ReactNode }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const instanceSeqRef = useRef(0)

  const showAlert = useCallback((config: AlertConfig) => {
    const { id, ...rest } = config
    const instanceKey = id ?? `alert-${++instanceSeqRef.current}`

    // Map 'error' to 'danger' for PatternFly compatibility
    let variant: AlertVariant = (config.variant as AlertVariant) || 'info'
    if (config.variant === 'error') {
      variant = 'danger'
    }

    const newAlert: AlertItem = {
      ...rest,
      instanceKey,
      variant,
    }

    setAlerts((prev) => [newAlert, ...prev])
  }, [])

  const showSuccess = useCallback(
    ({ title, description }: AlertMessage) => {
      showAlert({ variant: 'success', title, description, autoDismiss: true })
    },
    [showAlert]
  )

  const showError = useCallback(
    ({ title, description }: AlertMessage) => {
      showAlert({ variant: 'danger', title, description, autoDismiss: true })
    },
    [showAlert]
  )

  const showWarning = useCallback(
    ({ title, description }: AlertMessage) => {
      showAlert({ variant: 'warning', title, description, autoDismiss: true })
    },
    [showAlert]
  )

  const showInfo = useCallback(
    ({ title, description }: AlertMessage) => {
      showAlert({ variant: 'info', title, description, autoDismiss: true })
    },
    [showAlert]
  )

  const dismissAlert = useCallback((instanceKey: string) => {
    setAlerts((prev) => prev.filter((alert) => alert.instanceKey !== instanceKey))
  }, [])

  const clearAllAlerts = useCallback(() => {
    setAlerts([])
  }, [])

  const contextValue = useMemo(
    () => ({
      showAlert,
      showSuccess,
      showError,
      showWarning,
      showInfo,
      dismissAlert,
      clearAllAlerts,
    }),
    [showAlert, showSuccess, showError, showWarning, showInfo, dismissAlert, clearAllAlerts]
  )

  return (
    <AlertContext.Provider value={contextValue}>
      {children}
      <AlertGroup isToast isLiveRegion hasAnimations>
        {alerts.map((alert) => (
          <ToastAlertItem key={alert.instanceKey} alert={alert} onDismiss={dismissAlert} />
        ))}
      </AlertGroup>
    </AlertContext.Provider>
  )
}
