import {
  Button,
  FormGroup,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Spinner,
} from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiMinusCircleIcon, RhUiSyncIcon } from '@patternfly/react-icons'
import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationStatusEnum, IntegrationTypeEnum } from '@syntara/contracts'
import React, { type ReactElement, useCallback, useMemo, useState } from 'react'

import { SynLabel } from '../../../components/labels/SynLabel'
import { SynSelect } from '../../../components/SynSelect'
import { detachPromise } from '../../../utils/detachPromise'

import { resolveFormGroupLabelHelp } from './resolveFormGroupLabelHelp'
import { useAllIntegrations } from './useAllIntegrations'

type IntegrationRead =
  | IntegrationsAPI.components['schemas']['IntegrationRead']
  | IntegrationsAPI.components['schemas']['KafkaIntegrationRead']
type IntegrationStatus = (typeof IntegrationStatusEnum)[keyof typeof IntegrationStatusEnum]

const STATUS_CONFIG: Record<
  IntegrationStatus,
  { label: string; labelStatus: 'success' | 'danger' | 'custom'; Icon: React.ComponentType<{ className?: string }> }
> = {
  [IntegrationStatusEnum.AVAILABLE]: { label: 'Available', labelStatus: 'success', Icon: RhUiCheckCircleIcon },
  [IntegrationStatusEnum.ERROR]: { label: 'Error', labelStatus: 'danger', Icon: RhUiCloseCircleIcon },
  [IntegrationStatusEnum.VALIDATING]: { label: 'Validating', labelStatus: 'custom', Icon: RhUiSyncIcon },
  [IntegrationStatusEnum.UNKNOWN]: { label: 'Unknown', labelStatus: 'custom', Icon: RhUiMinusCircleIcon },
}

const NO_INTEGRATION_VALUE = '__none__'

function StatusBadge({ status }: Readonly<{ status: IntegrationStatus }>) {
  const config = STATUS_CONFIG[status]
  if (!config) return null
  const { label, labelStatus, Icon } = config
  return (
    <SynLabel variant="outline" status={labelStatus} icon={<Icon />}>
      {label}
    </SynLabel>
  )
}

function getIntegrationDescription(integration: IntegrationRead): string {
  const config = integration.configuration
  if (config && 'bootstrap_servers' in config) return config.bootstrap_servers.join(', ')
  if (config && 'base_url' in config) return String(config.base_url ?? '')
  return ''
}

export type IntegrationSelectorProps = {
  integrationType?: typeof IntegrationTypeEnum.MCP_SERVER | typeof IntegrationTypeEnum.KAFKA
  value?: string
  onChange: (integrationId: string | undefined) => void
  label?: string
  fieldId?: string
  isDisabled?: boolean
  isRequired?: boolean
  placeholder?: string
  helpText?: React.ReactNode
  /** When provided, filters integrations to those that are global or assigned to this project. */
  projectId?: string
  labelHelp?: ReactElement
}

function IntegrationMenuToggle(
  props: Readonly<{
    toggleRef: React.Ref<MenuToggleElement>
    ariaLabel: string
    displayText: string
    isOpen: boolean
    isDisabled: boolean
    isPending: boolean
    isError: boolean
    onClick: () => void
  }>
) {
  const { toggleRef, ariaLabel, displayText, isOpen, isDisabled, isPending, isError, onClick } = props
  return (
    <MenuToggle
      ref={toggleRef}
      onClick={onClick}
      isExpanded={isOpen}
      isDisabled={isDisabled || isPending}
      isFullWidth
      status={isError ? 'danger' : undefined}
      aria-label={ariaLabel}
      aria-busy={isPending || undefined}
    >
      {displayText}
      {isPending && (
        <>
          {' '}
          <Spinner size="sm" aria-hidden />
        </>
      )}
    </MenuToggle>
  )
}

/**
 * Select an MCP server or Kafka integration within the workflow's project scope.
 * Shows each integration's name, connection details and validation status.
 */
export function IntegrationSelector({
  value,
  onChange,
  label = 'MCP server integration',
  fieldId = 'integration-selector',
  isDisabled = false,
  isRequired = false,
  placeholder = 'Select an MCP server integration...',
  helpText,
  projectId,
  labelHelp,
  integrationType = IntegrationTypeEnum.MCP_SERVER,
}: Readonly<IntegrationSelectorProps>) {
  const [isOpen, setIsOpen] = useState(false)

  const isKafka = integrationType === IntegrationTypeEnum.KAFKA
  const emptyLabel = isKafka ? 'No Kafka integrations available' : 'No MCP server integrations available'
  const { data, isPending, isError, refetch } = useAllIntegrations(integrationType, projectId)
  const hasLoadedOptions = data !== undefined
  const isInitialPending = isPending && !hasLoadedOptions
  const isInitialError = isError && !hasLoadedOptions

  const integrations: IntegrationRead[] = useMemo(() => data ?? [], [data])

  const selectedIntegration = useMemo(() => integrations.find((i) => i.id === value), [integrations, value])

  const toggleLabel = useMemo(() => {
    if (isInitialError) return 'Error loading integrations'
    return (
      selectedIntegration?.name ?? (value && hasLoadedOptions ? 'Selected integration is unavailable' : placeholder)
    )
  }, [isInitialError, hasLoadedOptions, selectedIntegration?.name, placeholder, value])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selectedValue: string | number | undefined) => {
      setIsOpen(false)
      onChange(selectedValue === NO_INTEGRATION_VALUE ? undefined : String(selectedValue))
    },
    [onChange]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <IntegrationMenuToggle
        toggleRef={toggleRef}
        ariaLabel={label}
        displayText={toggleLabel}
        isOpen={isOpen}
        isDisabled={isDisabled}
        isPending={isInitialPending}
        isError={isError}
        onClick={() => setIsOpen((prev) => !prev)}
      />
    ),
    [label, toggleLabel, isOpen, isDisabled, isInitialPending, isError]
  )

  const resolvedLabelHelp = resolveFormGroupLabelHelp(label, labelHelp, helpText)

  return (
    <FormGroup label={label} labelHelp={resolvedLabelHelp} fieldId={fieldId} isRequired={isRequired}>
      <SynSelect
        id={fieldId}
        isOpen={isOpen}
        selected={value ?? NO_INTEGRATION_VALUE}
        onSelect={handleSelect}
        onOpenChange={setIsOpen}
        toggle={renderToggle}
        shouldFocusToggleOnSelect
      >
        <SelectList aria-label={`${label} options`}>
          <SelectOption value={NO_INTEGRATION_VALUE} isSelected={!value}>
            {isKafka ? 'Select a Kafka integration' : 'No integration (use direct connection)'}
          </SelectOption>
          {integrations.map((integration) => (
            <SelectOption
              key={integration.id}
              value={integration.id}
              isSelected={integration.id === value}
              description={getIntegrationDescription(integration)}
            >
              <span>{integration.name}</span>{' '}
              {integration.validation_status && <StatusBadge status={integration.validation_status} />}
            </SelectOption>
          ))}
          {integrations.length === 0 && !isInitialPending && (
            <SelectOption isDisabled value="__empty__">
              {isInitialError ? 'Failed to load integrations' : emptyLabel}
            </SelectOption>
          )}
        </SelectList>
      </SynSelect>

      {isError && (
        <Button variant="link" size="sm" onClick={() => detachPromise(refetch())}>
          Retry loading integrations
        </Button>
      )}
    </FormGroup>
  )
}
