import {
  Content,
  ContentVariants,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  type MenuToggleElement,
} from '@patternfly/react-core'
import { useCallback, useState, type Ref } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { FormFieldError } from '../../../components/FormFieldError'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { SynSelect } from '../../../components/SynSelect'
import { detachPromise } from '../../../utils/detachPromise'
import { StatusLabel } from '../../configuration/integrations/StatusLabel'
import { IntegrationRequiredHelper } from '../components/IntegrationRequiredHelper'
import { TypeaheadMenuToggle } from '../components/TypeaheadMenuToggle'

import type { TriggerFormData } from './triggerFormSchema'
import { kafkaResourceErrors, type KafkaSubscribeResources } from './useKafkaSubscribeResources'

/** Integration health describes the management connection, not runtime credential access. */
export function KafkaIntegrationField({
  isDisabled,
  resources,
}: Readonly<{ isDisabled: boolean; resources: KafkaSubscribeResources }>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterText, setFilterText] = useState('')
  const { control, setValue } = useFormContext<TriggerFormData>()
  const integrationId = useWatch({ control, name: 'integrationId' })
  const { integrations: query, visibleIntegrations: integrations } = resources
  const selected = integrations.find((item) => item.id === integrationId)
  const resourceError = kafkaResourceErrors({ triggerType: '', integrationId }, resources).integrationId
  const visible = integrations.filter((item) => item.name.toLowerCase().includes(filterText.trim().toLowerCase()))
  const errorId = 'kafka-integration-error'
  const changeIntegration = useCallback(
    (value: string) => {
      setValue('integrationId', value, { shouldDirty: true, shouldValidate: true })
      setValue('runtimeCredentialId', '', { shouldDirty: true, shouldValidate: true })
    },
    [setValue]
  )
  const renderToggle = useCallback(
    (ref: Ref<MenuToggleElement>) => (
      <TypeaheadMenuToggle
        toggleRef={ref}
        displayText={selected?.name ?? (integrationId ? 'Selected Integration unavailable' : '')}
        ariaLabel="Kafka Integration"
        fieldId="kafka-integration"
        isOpen={isOpen}
        isDisabled={isDisabled || query.isError}
        isPending={query.isPending}
        hasSelection={Boolean(integrationId)}
        filterText={filterText}
        placeholder="Select a Kafka Integration"
        loadingPlaceholder="Loading Kafka Integrations…"
        onFilterChange={setFilterText}
        onClear={() => changeIntegration('')}
        onToggle={() => setIsOpen(!isOpen)}
        isInvalid={Boolean(resourceError)}
        describedBy={resourceError ? errorId : undefined}
      />
    ),
    [
      selected?.name,
      integrationId,
      isOpen,
      isDisabled,
      query.isError,
      query.isPending,
      filterText,
      changeIntegration,
      resourceError,
    ]
  )

  return (
    <Stack hasGutter>
      <StackItem>
        <SynFormField<TriggerFormData, 'integrationId'>
          name="integrationId"
          label="Kafka Integration"
          fieldId="kafka-integration"
          isRequired
          hideFooter
        >
          {({ field }) => (
            <SynSelect
              id="kafka-integration"
              isOpen={isOpen}
              selected={field.value}
              toggle={renderToggle}
              shouldFocusToggleOnSelect
              onOpenChange={(open) => {
                setIsOpen(open)
                if (!open) setFilterText('')
              }}
              onSelect={(_event, value) => {
                if (typeof value !== 'string' || !integrations.some((item) => item.id === value)) return
                changeIntegration(value)
                setFilterText('')
                setIsOpen(false)
              }}
            >
              <SelectList aria-label="Kafka Integrations">
                {visible.map((item) => (
                  <SelectOption key={item.id} value={item.id} isSelected={item.id === field.value}>
                    {item.name}
                  </SelectOption>
                ))}
                {!query.isPending && !query.isError && !visible.length && (
                  <SelectOption value="__empty__" isDisabled>
                    {filterText ? 'No matching Kafka Integrations' : 'No Kafka Integrations available'}
                  </SelectOption>
                )}
              </SelectList>
            </SynSelect>
          )}
        </SynFormField>
        <FormFieldError id={errorId} message={resourceError} />
      </StackItem>
      {query.isError && (
        <StackItem>
          <SynErrorState
            title="Unable to load Kafka Integrations"
            message={query.error}
            onRetry={() => detachPromise(query.refetch())}
          />
        </StackItem>
      )}
      {!query.isPending && !query.isError && !integrations.length && (
        <StackItem>
          <IntegrationRequiredHelper
            integrationLabel="a Kafka Integration"
            actionLabel="a Kafka Integration can be selected"
          />
        </StackItem>
      )}
      {selected && (
        <StackItem>
          <Content component={ContentVariants.p}>
            Integration validation:{' '}
            <StatusLabel status={selected.validation_status ?? 'unknown'} errorMessage={selected.validation_error} />.
            This describes the managed connection, not the selected runtime credential’s access.
          </Content>
        </StackItem>
      )}
    </Stack>
  )
}
