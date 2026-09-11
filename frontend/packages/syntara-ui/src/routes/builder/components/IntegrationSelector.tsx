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

import { integrationsClient } from '../../../client'
import { SynLabel } from '../../../components/labels/SynLabel'
import { SynSelect } from '../../../components/SynSelect'
import { detachPromise } from '../../../utils/detachPromise'
import { projectIdParam } from '../../../utils/queryParams'

import { resolveFormGroupLabelHelp } from './resolveFormGroupLabelHelp'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']
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

function getIntegrationBaseUrl(integration: IntegrationRead): string {
  const config = integration.configuration
  if (config && 'base_url' in config) return String(config.base_url ?? '')
  return ''
}

export type IntegrationSelectorProps = {
  value?: string
  onChange: (integrationId: string | undefined) => void
  label?: string
  fieldId?: string
  isDisabled?: boolean
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
    >
      {isPending ? (
        <>
          <Spinner size="sm" aria-hidden /> Loading integrations...
        </>
      ) : (
        displayText
      )}
    </MenuToggle>
  )
}

/**
 * A PatternFly Select dropdown for choosing an MCP server integration.
 * Fetches integrations from the API filtered to mcp_server type.
 * Displays each integration's name and validation status badge.
 */
export function IntegrationSelector({
  value,
  onChange,
  label = 'MCP server integration',
  fieldId = 'integration-selector',
  isDisabled = false,
  placeholder = 'Select an MCP server integration...',
  helpText,
  projectId,
  labelHelp,
}: Readonly<IntegrationSelectorProps>) {
  const [isOpen, setIsOpen] = useState(false)

  const { data, isPending, isError, refetch } = integrationsClient.useQuery('get', '/integrations', {
    params: {
      query: {
        integration_type: IntegrationTypeEnum.MCP_SERVER,
        enabled: true,
        ...projectIdParam(projectId),
      },
    },
  })

  const integrations: IntegrationRead[] = useMemo(() => data?.resources ?? [], [data?.resources])

  const selectedIntegration = useMemo(() => integrations.find((i) => i.id === value), [integrations, value])

  const toggleLabel = useMemo(() => {
    if (isPending) return 'Loading integrations...'
    if (isError) return 'Error loading integrations'
    return selectedIntegration?.name ?? placeholder
  }, [isPending, isError, selectedIntegration?.name, placeholder])

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
        isPending={isPending}
        isError={isError}
        onClick={() => setIsOpen((prev) => !prev)}
      />
    ),
    [label, toggleLabel, isOpen, isDisabled, isPending, isError]
  )

  const resolvedLabelHelp = resolveFormGroupLabelHelp(label, labelHelp, helpText)

  return (
    <FormGroup label={label} labelHelp={resolvedLabelHelp} fieldId={fieldId}>
      <SynSelect
        id={fieldId}
        isOpen={isOpen}
        selected={value ?? NO_INTEGRATION_VALUE}
        onSelect={handleSelect}
        onOpenChange={setIsOpen}
        toggle={renderToggle}
        shouldFocusToggleOnSelect
      >
        <SelectList aria-label="MCP server integration options">
          <SelectOption value={NO_INTEGRATION_VALUE} isSelected={!value}>
            No integration (use direct connection)
          </SelectOption>
          {integrations.map((integration) => (
            <SelectOption
              key={integration.id}
              value={integration.id}
              isSelected={integration.id === value}
              description={getIntegrationBaseUrl(integration)}
            >
              <span>{integration.name}</span>{' '}
              {integration.validation_status && <StatusBadge status={integration.validation_status} />}
            </SelectOption>
          ))}
          {integrations.length === 0 && !isPending && (
            <SelectOption isDisabled value="__empty__">
              {isError ? 'Failed to load integrations' : 'No MCP server integrations available'}
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
