import {
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
import { useNavigate } from '@tanstack/react-router'
import React, { useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { AppRoute } from '../../../app/AppRoute'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { SynSelect } from '../../../components/SynSelect'
import { detachPromise } from '../../../utils/detachPromise'
import { useExecutionTargetPermissions } from '../../execution-plane/useExecutionTargetPermissions'
import { ScriptAffinityEnum, type ScriptAffinity } from '../utils/scriptExecutionProfile'
import { useIsVersionView } from '../VersionViewContext'

import type { ActionFormValues } from './actionFormSchema'
import { stepHelp } from './shared/stepFieldHelp'
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

type AffinitySelectProps = {
  value: ScriptAffinity
  onChange: (value: ScriptAffinity) => void
  isDisabled?: boolean
}

function AffinitySelect({ value, onChange, isDisabled }: AffinitySelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = AFFINITY_OPTIONS.find((option) => option.value === value)?.label

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
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isDisabled={isDisabled}
          aria-label="Affinity"
        >
          {selectedLabel ?? value}
        </MenuToggle>
      )}
    >
      <SelectList>
        {AFFINITY_OPTIONS.map((option) => (
          <SelectOption
            key={option.value}
            value={option.value}
            description={option.description}
            isSelected={option.value === value}
          >
            {option.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

type ExecutionTargetSelectProps = {
  value: string
  onChange: (value: string) => void
  targets: ExecutionTargetRead[]
  isLoading: boolean
  isDisabled?: boolean
}

function ExecutionTargetSelect({ value, onChange, targets, isLoading, isDisabled }: ExecutionTargetSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = targets.find((target) => target.id === value)?.name

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
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isDisabled={isDisabled || isLoading}
          aria-label="Execution target"
        >
          {isLoading ? (
            <Spinner size="sm" aria-label="Loading execution targets" />
          ) : (
            (selectedLabel ?? 'Select execution target')
          )}
        </MenuToggle>
      )}
    >
      <SelectList>
        {targets.map((target) => (
          <SelectOption key={target.id} value={target.id} isSelected={target.id === value}>
            {target.name}
          </SelectOption>
        ))}
        {!isLoading && targets.length === 0 && (
          <SelectOption isDisabled value="none">
            No execution targets available
          </SelectOption>
        )}
      </SelectList>
    </SynSelect>
  )
}

function NoExecutionTargetsGuidance({ canConfigure }: { canConfigure: boolean }) {
  const navigate = useNavigate()

  return (
    <EmptyState headingLevel="h3" titleText="No execution targets yet" icon={PlusCircleIcon}>
      <EmptyStateBody>
        Configure an execution target to register compute capacity before pinning a script to a required target.
      </EmptyStateBody>
      {canConfigure && (
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button
              variant="primary"
              icon={<RhUiAddIcon />}
              onClick={() => detachPromise(navigate({ to: AppRoute.ExecutionPlane.Create }))}
            >
              Configure execution target
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      )}
    </EmptyState>
  )
}

/**
 * Mounted only when Affinity is Required target so the targets list query
 * does not run on the default None path.
 */
function RequiredTargetFields({ isDisabled }: { isDisabled: boolean }) {
  const { targets, isLoading, isError, error, refetch } = useAllEnabledExecutionTargets()
  const permissions = useExecutionTargetPermissions()

  if (isError) {
    return (
      <SynErrorState title="Error loading execution targets" message={error} onRetry={() => detachPromise(refetch())} />
    )
  }

  if (!isLoading && targets.length === 0) {
    return <NoExecutionTargetsGuidance canConfigure={permissions.canCreate} />
  }

  return (
    <SynFormField
      name="execution_target_id"
      label="Execution target"
      labelHelp={stepHelp.scriptExecutionTarget}
      isRequired
      fieldId="script-execution-target"
    >
      {({ field }) => (
        <ExecutionTargetSelect
          value={typeof field.value === 'string' ? field.value : ''}
          onChange={field.onChange}
          targets={targets}
          isLoading={isLoading}
          isDisabled={isDisabled}
        />
      )}
    </SynFormField>
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
  const watchedAffinity = useWatch<ActionFormValues, 'affinity'>({ name: 'affinity' })
  const affinity = toScriptAffinity(watchedAffinity)
  const showRequiredTarget = affinity === ScriptAffinityEnum.REQUIRED_TARGET

  return (
    <Stack hasGutter style={{ paddingInline: 'var(--pf-t--global--spacer--xs)' }}>
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
              isDisabled={isVersionView}
            />
          )}
        </SynFormField>
      </StackItem>

      {showRequiredTarget && (
        <StackItem>
          <RequiredTargetFields isDisabled={isVersionView} />
        </StackItem>
      )}
    </Stack>
  )
}
