import {
  Alert,
  AlertActionLink,
  Button,
  Content,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Spinner,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { PlusCircleIcon, RhUiAddIcon } from '@patternfly/react-icons'
import React, { useCallback, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { AppRoute } from '../../../app/AppRoute'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { SynSelect } from '../../../components/SynSelect'
import { detachPromise } from '../../../utils/detachPromise'
import {
  useExecutionTargetPermissions,
  type ExecutionTargetPermissions,
} from '../../execution-plane/useExecutionTargetPermissions'
import { ScriptAffinityEnum, type ScriptAffinity } from '../utils/scriptExecutionProfile'
import { useIsVersionView } from '../VersionViewContext'

import type { ActionFormValues } from './actionFormSchema'
import { stepHelp } from './shared/stepFieldHelp'
import stepFormStyles from './shared/stepFormStyles.module.css'
import { useAllEnabledExecutionTargets, type ExecutionTargetRead } from './useAllEnabledExecutionTargets'

const AFFINITY_OPTIONS: Array<{ value: ScriptAffinity; label: string; description: string }> = [
  {
    value: ScriptAffinityEnum.REQUIRED_TARGET,
    label: 'Required target',
    description: 'Run only on a specific execution target. Use when a workload must land on one worker.',
  },
  {
    value: ScriptAffinityEnum.NONE,
    label: 'None',
    description: 'Let the execution plane choose placement based on availability and connectivity.',
  },
]

type AffinityMenuToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  isDisabled?: boolean
  label: string
  onToggle: () => void
}>

function AffinityMenuToggle({ toggleRef, isOpen, isDisabled, label, onToggle }: AffinityMenuToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      onClick={onToggle}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      aria-label="Affinity"
    >
      {label}
    </MenuToggle>
  )
}

function renderAffinityToggle(
  toggleRef: React.Ref<MenuToggleElement>,
  state: Omit<AffinityMenuToggleProps, 'toggleRef'>
) {
  return <AffinityMenuToggle toggleRef={toggleRef} {...state} />
}

type AffinitySelectProps = Readonly<{
  value: ScriptAffinity
  onChange: (value: ScriptAffinity) => void
  isDisabled?: boolean
  /** Safe-false: only true after can_i confirms execution_target:read. */
  canSelectRequiredTarget: boolean
  requiredTargetAccessMessage: string
}>

function AffinitySelect({
  value,
  onChange,
  isDisabled,
  canSelectRequiredTarget,
  requiredTargetAccessMessage,
}: AffinitySelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = AFFINITY_OPTIONS.find((option) => option.value === value)?.label ?? value
  const handleToggle = useCallback(() => setIsOpen((prev) => !prev), [])
  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) =>
      renderAffinityToggle(toggleRef, {
        isOpen,
        isDisabled,
        label: selectedLabel,
        onToggle: handleToggle,
      }),
    [handleToggle, isDisabled, isOpen, selectedLabel]
  )

  return (
    <SynSelect
      id="script-affinity"
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, selected) => {
        onChange(toScriptAffinity(selected))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={renderToggle}
    >
      <SelectList>
        {AFFINITY_OPTIONS.map((option) => {
          const isRequiredTarget = option.value === ScriptAffinityEnum.REQUIRED_TARGET
          // Keep Required target disabled until read access is confirmed
          const isOptionDisabled = isRequiredTarget && !canSelectRequiredTarget
          return (
            <SelectOption
              key={option.value}
              value={option.value}
              description={isOptionDisabled ? requiredTargetAccessMessage : option.description}
              isDisabled={isOptionDisabled}
              isSelected={option.value === value}
            >
              {option.label}
            </SelectOption>
          )
        })}
      </SelectList>
    </SynSelect>
  )
}

type ExecutionTargetMenuToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  isDisabled?: boolean
  isLoading: boolean
  hasError?: boolean
  label: string
  onToggle: () => void
}>

function ExecutionTargetMenuToggle({
  toggleRef,
  isOpen,
  isDisabled,
  isLoading,
  hasError,
  label,
  onToggle,
}: ExecutionTargetMenuToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      onClick={onToggle}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled || isLoading}
      status={hasError ? 'danger' : undefined}
      aria-label="Execution target"
    >
      {isLoading ? <Spinner size="sm" aria-label="Loading execution targets" /> : label}
    </MenuToggle>
  )
}

function renderExecutionTargetToggle(
  toggleRef: React.Ref<MenuToggleElement>,
  state: Omit<ExecutionTargetMenuToggleProps, 'toggleRef'>
) {
  return <ExecutionTargetMenuToggle toggleRef={toggleRef} {...state} />
}

const UNAVAILABLE_TARGET_LABEL = 'Unavailable execution target'
const UNAVAILABLE_TARGET_DESCRIPTION = 'This target is disabled or no longer exists'
export const UNAVAILABLE_TARGET_ERROR =
  'The selected execution target is unavailable. Choose an available target, or clear the unavailable target.'
export const CLEAR_UNAVAILABLE_TARGET_LABEL = 'Clear unavailable target'

type ExecutionTargetSelectProps = Readonly<{
  value: string
  onChange: (value: string) => void
  targets: ExecutionTargetRead[]
  isLoading: boolean
  isUnavailable: boolean
  isDisabled?: boolean
  hasError?: boolean
}>

function ExecutionTargetSelect({
  value,
  onChange,
  targets,
  isLoading,
  isUnavailable,
  isDisabled,
  hasError,
}: ExecutionTargetSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = isUnavailable
    ? UNAVAILABLE_TARGET_LABEL
    : (targets.find((target) => target.id === value)?.name ?? 'Select execution target')
  const handleToggle = useCallback(() => setIsOpen((prev) => !prev), [])
  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) =>
      renderExecutionTargetToggle(toggleRef, {
        isOpen,
        isDisabled,
        isLoading,
        hasError: hasError || isUnavailable,
        label: selectedLabel,
        onToggle: handleToggle,
      }),
    [handleToggle, hasError, isDisabled, isLoading, isOpen, isUnavailable, selectedLabel]
  )

  return (
    <SynSelect
      id="script-execution-target"
      isOpen={isOpen}
      selected={value || undefined}
      onSelect={(_event, selected) => {
        onChange(String(selected))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={renderToggle}
    >
      <SelectList>
        {isUnavailable && value && (
          <SelectOption value={value} isDisabled isSelected description={UNAVAILABLE_TARGET_DESCRIPTION}>
            {UNAVAILABLE_TARGET_LABEL}
          </SelectOption>
        )}
        {targets.map((target) => (
          <SelectOption key={target.id} value={target.id} isSelected={target.id === value}>
            {target.name}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

function NoExecutionTargetsGuidance({ canConfigure }: Readonly<{ canConfigure: boolean }>) {
  return (
    <EmptyState headingLevel="h3" titleText="No execution targets yet" icon={PlusCircleIcon}>
      <EmptyStateBody>
        Configure an execution target to register compute capacity before pinning a script to a required target. Opens
        in a new tab so your step draft stays open.
      </EmptyStateBody>
      {canConfigure && (
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button
              variant="primary"
              icon={<RhUiAddIcon />}
              component="a"
              href={AppRoute.ExecutionPlane.Create}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Configure execution target (opens in a new tab)"
            >
              Configure execution target
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      )}
    </EmptyState>
  )
}

function UnavailableTargetWarning({ isDisabled, onClear }: Readonly<{ isDisabled?: boolean; onClear: () => void }>) {
  return (
    <Alert
      variant="warning"
      title={UNAVAILABLE_TARGET_LABEL}
      isInline
      actionLinks={
        isDisabled ? undefined : <AlertActionLink onClick={onClear}>{CLEAR_UNAVAILABLE_TARGET_LABEL}</AlertActionLink>
      }
    >
      {UNAVAILABLE_TARGET_ERROR}
    </Alert>
  )
}

/**
 * Mounted only when Affinity is Required target and the user can read targets,
 * so the list query does not run on the default None path or without permission.
 */
function RequiredTargetFields({ isDisabled, canConfigure }: Readonly<{ isDisabled: boolean; canConfigure: boolean }>) {
  const { targets, isLoading, isError, error, refetch } = useAllEnabledExecutionTargets()
  const { getValues, setValue } = useFormContext<ActionFormValues>()
  const watchedTargetId = useWatch<ActionFormValues, 'execution_target_id'>({ name: 'execution_target_id' })
  const valueFromWatch = typeof watchedTargetId === 'string' ? watchedTargetId : ''
  // useWatch can be empty before SynFormField registers the input; fall back to form values
  // so a saved disabled-target ID is still detected on the empty-list path.
  const valueFromForm = getValues('execution_target_id')
  const value = valueFromWatch || (typeof valueFromForm === 'string' ? valueFromForm : '')
  const isUnavailable = !isLoading && !isError && value !== '' && !targets.some((target) => target.id === value)

  // Clear only from an explicit user action. Do not auto-clear or setError on mount — that
  // leaves REQUIRED_TARGET with a missing/errored field, and Save/Update then fails silently
  // when the Execution tab (the only place that shows the message) is not visible.
  const handleClearUnavailableTarget = useCallback(() => {
    setValue('execution_target_id', undefined, { shouldDirty: true, shouldValidate: true })
    setValue('affinity', ScriptAffinityEnum.NONE, { shouldDirty: true, shouldValidate: true })
  }, [setValue])

  if (isError) {
    return (
      <SynErrorState title="Error loading execution targets" message={error} onRetry={() => detachPromise(refetch())} />
    )
  }

  if (!isLoading && targets.length === 0) {
    return (
      <Stack hasGutter>
        {isUnavailable && <UnavailableTargetWarning isDisabled={isDisabled} onClear={handleClearUnavailableTarget} />}
        <NoExecutionTargetsGuidance canConfigure={canConfigure} />
      </Stack>
    )
  }

  return (
    <Stack hasGutter>
      {isUnavailable && <UnavailableTargetWarning isDisabled={isDisabled} onClear={handleClearUnavailableTarget} />}
      <SynFormField
        name="execution_target_id"
        label="Execution target"
        labelHelp={stepHelp.scriptExecutionTarget}
        isRequired
        fieldId="script-execution-target"
      >
        {({ field, fieldState }) => (
          <ExecutionTargetSelect
            value={typeof field.value === 'string' ? field.value : ''}
            onChange={field.onChange}
            targets={targets}
            isLoading={isLoading}
            isUnavailable={isUnavailable}
            isDisabled={isDisabled}
            hasError={!!fieldState.error || isUnavailable}
          />
        )}
      </SynFormField>
    </Stack>
  )
}

function RequiredTargetAccessDenied({ message }: Readonly<{ message: string }>) {
  return (
    <Alert variant="warning" title="Cannot list execution targets" isInline>
      {message}
    </Alert>
  )
}

function toScriptAffinity(value: unknown): ScriptAffinity {
  if (value === ScriptAffinityEnum.REQUIRED_TARGET || value === ScriptAffinityEnum.NONE) {
    return value
  }
  return ScriptAffinityEnum.NONE
}

export function ScriptExecutionTab() {
  const { setValue } = useFormContext<ActionFormValues>()
  const isVersionView = useIsVersionView()
  const permissions: ExecutionTargetPermissions = useExecutionTargetPermissions()
  const canSelectRequiredTarget = permissions.canRead
  const requiredTargetAccessMessage = permissions.tooltips.read
  const watchedAffinity = useWatch<ActionFormValues, 'affinity'>({ name: 'affinity' })
  const affinity = toScriptAffinity(watchedAffinity)
  const showRequiredTarget = affinity === ScriptAffinityEnum.REQUIRED_TARGET

  let requiredTargetContent: React.ReactNode = null
  if (showRequiredTarget) {
    if (permissions.isLoading) {
      requiredTargetContent = <Spinner size="md" aria-label="Checking execution target permissions" />
    } else if (permissions.canRead) {
      requiredTargetContent = <RequiredTargetFields isDisabled={isVersionView} canConfigure={permissions.canCreate} />
    } else {
      requiredTargetContent = <RequiredTargetAccessDenied message={requiredTargetAccessMessage} />
    }
  }

  return (
    <Stack hasGutter className={stepFormStyles.tabContentStack}>
      <StackItem>
        <Content component="p">Choose where this step runs on the execution plane.</Content>
      </StackItem>

      <StackItem>
        <SynFormField
          name="affinity"
          label="Affinity"
          labelHelp={stepHelp.scriptAffinity}
          isRequired
          fieldId="script-affinity"
        >
          {({ field }) => (
            <AffinitySelect
              value={toScriptAffinity(field.value)}
              onChange={(nextAffinity) => {
                field.onChange(nextAffinity)
                if (nextAffinity !== ScriptAffinityEnum.REQUIRED_TARGET) {
                  setValue('execution_target_id', undefined)
                }
              }}
              isDisabled={isVersionView || permissions.isLoading}
              canSelectRequiredTarget={canSelectRequiredTarget}
              requiredTargetAccessMessage={requiredTargetAccessMessage}
            />
          )}
        </SynFormField>
      </StackItem>

      {requiredTargetContent && <StackItem>{requiredTargetContent}</StackItem>}
    </Stack>
  )
}
