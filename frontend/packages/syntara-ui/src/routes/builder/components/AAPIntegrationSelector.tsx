import { FormGroup, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationTypeEnum } from '@syntara/contracts'
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { integrationsClient } from '../../../client'
import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { SynSelect } from '../../../components/SynSelect'
import { projectIdParam } from '../../../utils/queryParams'

import styles from './AAPIntegrationSelector.module.css'
import { IntegrationRequiredHelper } from './IntegrationRequiredHelper'
import { TypeaheadMenuToggle } from './TypeaheadMenuToggle'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

export type AAPIntegrationSelectorProps = {
  value?: string
  onChange: (integrationId: string | undefined) => void
  label?: string
  fieldId?: string
  isDisabled?: boolean
  isRequired?: boolean
  helpText?: React.ReactNode
  /** When provided, filters AAP integrations to those that are global or assigned to this project. */
  projectId?: string
  /** Called when integrations finish loading and the currently selected integration is not found. */
  onStaleDetected?: () => void
}

function getIntegrationUrl(integration: IntegrationRead): string | undefined {
  const config = integration.configuration
  if (config && 'base_url' in config) {
    return config.base_url ?? undefined
  }
  return undefined
}

export function AAPIntegrationSelector({
  value,
  onChange,
  label = 'Integration',
  fieldId = 'aap-integration-selector',
  isDisabled = false,
  isRequired = false,
  helpText,
  projectId,
  onStaleDetected,
}: Readonly<AAPIntegrationSelectorProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterText, setFilterText] = useState('')

  const {
    data: integrationsData,
    isPending,
    isError,
  } = integrationsClient.useQuery('get', '/integrations', {
    params: {
      query: {
        integration_type: IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM,
        enabled: true,
        ...projectIdParam(projectId),
      },
    },
  })

  const integrations: (IntegrationRead & { id: string })[] = useMemo(
    () => (integrationsData?.resources ?? []).filter((i): i is IntegrationRead & { id: string } => !!i.id),
    [integrationsData?.resources]
  )

  const staleFiredForRef = useRef<string | null>(null)
  useEffect(() => {
    if (isPending || isError || !value) return
    if (staleFiredForRef.current === value) return
    if (integrations.some((i) => i.id === value)) return
    staleFiredForRef.current = value
    onStaleDetected?.()
  }, [isPending, isError, value, integrations, onStaleDetected])

  const visibleIntegrations = useMemo(() => {
    const query = filterText.toLowerCase().trim()
    if (!query) return integrations
    return integrations.filter((i) => i.name.toLowerCase().includes(query))
  }, [integrations, filterText])

  const toggleLabel = useMemo(() => {
    if (!value) return ''
    const found = integrations.find((i) => i.id === value)
    return found?.name ?? value
  }, [value, integrations])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selectedValue: string | number | undefined) => {
      setIsOpen(false)
      setFilterText('')
      if (!selectedValue || typeof selectedValue !== 'string') {
        onChange(undefined)
        return
      }
      onChange(selectedValue)
    },
    [onChange]
  )

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterText('')
  }, [])

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <TypeaheadMenuToggle
        toggleRef={toggleRef}
        displayText={toggleLabel}
        ariaLabel={label}
        fieldId={fieldId}
        isOpen={isOpen}
        isDisabled={isDisabled}
        isPending={isPending}
        hasSelection={!!value}
        filterText={filterText}
        placeholder="Select an Ansible Automation Platform integration"
        loadingPlaceholder="Loading integrations..."
        onFilterChange={setFilterText}
        onClear={() => onChange(undefined)}
        onToggle={() => setIsOpen((prev) => !prev)}
      />
    ),
    [toggleLabel, label, fieldId, isOpen, isDisabled, isPending, value, filterText, onChange]
  )

  const formGroupLabel = helpText ? <FormLabelWithHelp label={label} helpText={helpText} /> : label

  return (
    <FormGroup label={formGroupLabel} fieldId={fieldId} isRequired={isRequired}>
      <SynSelect
        id={fieldId}
        isOpen={isOpen}
        selected={value}
        onSelect={handleSelect}
        onOpenChange={handleOpenChange}
        toggle={renderToggle}
        shouldFocusToggleOnSelect
      >
        <SelectList>
          {integrations.length === 0 && !isPending && (
            <SelectOption isAriaDisabled value="__empty__">
              No AAP integrations configured
            </SelectOption>
          )}
          {filterText && visibleIntegrations.length === 0 && (
            <SelectOption isAriaDisabled value="__no_results__">
              No results match &quot;{filterText}&quot;
            </SelectOption>
          )}
          {visibleIntegrations.map((integration) => {
            const url = getIntegrationUrl(integration)
            return (
              <SelectOption key={integration.id} value={integration.id} isSelected={value === integration.id}>
                <span className={styles.integrationOptionContent}>
                  <span>{integration.name}</span>
                  {url && <span className={styles.integrationUrl}>{url}</span>}
                </span>
              </SelectOption>
            )
          })}
        </SelectList>
      </SynSelect>

      {!isPending && integrations.length === 0 && (
        <IntegrationRequiredHelper integrationLabel="an AAP integration" actionLabel="an integration can be selected" />
      )}
    </FormGroup>
  )
}
