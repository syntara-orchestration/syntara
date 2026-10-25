import { Button, Dropdown, DropdownItem, DropdownList, MenuToggle } from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'
import { useRef, useState } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'
import { useDialogState } from '../../hooks/useDialogState'
import { detachPromise } from '../../utils/detachPromise'

import { useIsCurrentVersion } from './hooks/useIsCurrentVersion'
import { RetryExecutionDialog } from './RetryExecutionDialog'
import { RetryFromFailureButton } from './RetryFromFailureButton'
import { useRetryExecution } from './useRetryExecution'

type RetryExecutionButtonProps = Readonly<{
  executionId: string
  workflowId: string
  workflowVersionId: string
  projectId: string
  retryFromFailure?: Readonly<{
    projectId: string
    onClick?: () => void
  }>
}>

const retryTooltip = permissionTooltip('retry this execution', 'execution:run')

export function RetryExecutionButton({
  executionId,
  workflowId,
  workflowVersionId,
  projectId,
  retryFromFailure,
}: RetryExecutionButtonProps) {
  const retryDialog = useDialogState<void>()
  const navigate = useNavigate()
  const [isRetryMenuOpen, setIsRetryMenuOpen] = useState(false)
  const retryMenuToggleRef = useRef<MenuToggleElement>(null)

  /* v8 ignore start -- v8 emits phantom branches from compiled hook destructuring */
  const { allowed: canRun, isChecking } = useCanI('run', 'execution', { resourceProject: projectId })
  const permissionDenied = !isChecking && !canRun
  const isDisabled = !canRun || isChecking

  const {
    isCurrentVersion,
    versionLabel,
    isLoading: isVersionLoading,
  } = useIsCurrentVersion(workflowId, workflowVersionId, retryDialog.isOpen)

  const retry = useRetryExecution(executionId, (newExecutionId) => {
    retryDialog.close()
    detachPromise(navigate({ to: AppRoute.Executions.Execution.replace(':executionId', newExecutionId) }))
  })
  /* v8 ignore stop */

  const retryTrigger = retryFromFailure ? (
    <Dropdown
      isOpen={isRetryMenuOpen}
      onOpenChange={setIsRetryMenuOpen}
      onSelect={(_event, value) => {
        setIsRetryMenuOpen(false)
        if (value === 'retry-from-failure') {
          requestAnimationFrame(() => retryMenuToggleRef.current?.focus())
        }
      }}
      popperProps={{ position: 'end' }}
      toggle={(toggleRef) => (
        <MenuToggle
          ref={(node) => {
            retryMenuToggleRef.current = node
            toggleRef.current = node
          }}
          variant="secondary"
          onClick={() => setIsRetryMenuOpen((isOpen) => !isOpen)}
          isExpanded={isRetryMenuOpen}
        >
          Retry run
        </MenuToggle>
      )}
    >
      <DropdownList>
        <DropdownItem
          value="retry-run"
          onClick={isDisabled ? undefined : () => retryDialog.open(undefined)}
          isAriaDisabled={isDisabled}
          tooltipProps={permissionDenied ? { content: retryTooltip } : undefined}
        >
          Retry run
        </DropdownItem>
        <RetryFromFailureButton
          projectId={retryFromFailure.projectId}
          onClick={retryFromFailure.onClick}
          asDropdownItem
        />
      </DropdownList>
    </Dropdown>
  ) : (
    <DisabledWithTooltip isDisabled={permissionDenied} content={retryTooltip}>
      <Button
        variant="secondary"
        onClick={isDisabled ? undefined : () => retryDialog.open(undefined)}
        isAriaDisabled={isDisabled}
      >
        Retry run
      </Button>
    </DisabledWithTooltip>
  )

  return (
    <>
      {retryTrigger}
      <RetryExecutionDialog
        isOpen={retryDialog.isOpen}
        onClose={retryDialog.close}
        onConfirm={retry.handleRetry}
        confirmLoading={retry.isPending || isVersionLoading}
        isCurrentVersion={isCurrentVersion}
        isVersionLoading={isVersionLoading}
        versionLabel={versionLabel}
      />
    </>
  )
}
