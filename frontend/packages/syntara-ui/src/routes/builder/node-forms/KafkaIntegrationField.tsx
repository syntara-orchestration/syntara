import {
  Content,
  ContentVariants,
  MenuToggle,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { integrationsFetchClient } from '../../../client'
import { FormFieldError } from '../../../components/FormFieldError'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { SynSelect } from '../../../components/SynSelect'
import { detachPromise } from '../../../utils/detachPromise'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'
import { projectIdParam } from '../../../utils/queryParams'

import type { TriggerFormData } from './triggerFormSchema'

/** Lists visible, enabled Kafka Integrations; Integration health is not runtime access. */
export function KafkaIntegrationField({
  projectId,
  isDisabled,
}: Readonly<{ projectId?: string; isDisabled: boolean }>) {
  const [isOpen, setIsOpen] = useState(false)
  const {
    control,
    setValue,
    clearErrors,
    formState: { errors },
  } = useFormContext<TriggerFormData>()
  const integrationId = useWatch({ control, name: 'integrationId' })
  const query = useQuery({
    queryKey: ['kafka-subscribe-integrations', projectId],
    queryFn: () =>
      fetchAllPages((cursor) =>
        integrationsFetchClient.GET('/kafka_integrations', {
          params: {
            query: {
              enabled: true,
              limit: MAX_PAGE_SIZE,
              cursor,
              ...projectIdParam(projectId),
            },
          },
        })
      ),
  })
  const integrations = useMemo(
    () => query.data?.filter((item) => item.integration_type === IntegrationTypeEnum.KAFKA && item.enabled) ?? [],
    [query.data]
  )
  const selected = integrations.find((item) => item.id === integrationId)
  const staleSelection = Boolean(integrationId && !query.isPending && !query.isError && !selected)

  const integrationError = staleSelection ? 'Select an available Kafka Integration' : errors.integrationId?.message
  const errorId = 'kafka-integration-error'

  const selectionLabel =
    selected?.name ?? (integrationId ? 'Selected Integration unavailable' : 'Select a Kafka Integration')
  const toggleLabel = query.isPending ? 'Loading Kafka Integrations…' : selectionLabel

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
              onOpenChange={setIsOpen}
              shouldFocusToggleOnSelect
              onSelect={(_event, value) => {
                if (typeof value !== 'string') return
                field.onChange(value)
                setValue('runtimeCredentialId', '', { shouldDirty: true })
                clearErrors('runtimeCredentialId')
                setIsOpen(false)
              }}
              toggle={(ref) => (
                <MenuToggle
                  ref={ref}
                  aria-label="Kafka Integration"
                  aria-invalid={Boolean(integrationError)}
                  aria-describedby={integrationError ? errorId : undefined}
                  isFullWidth
                  isDisabled={isDisabled || query.isPending || query.isError}
                  isExpanded={isOpen}
                  onClick={() => setIsOpen(!isOpen)}
                >
                  {toggleLabel}
                </MenuToggle>
              )}
            >
              <SelectList aria-label="Kafka Integrations">
                {integrations.map((item) => (
                  <SelectOption key={item.id} value={item.id} isSelected={item.id === field.value}>
                    {item.name}
                  </SelectOption>
                ))}
                {!integrations.length && (
                  <SelectOption value="__empty__" isDisabled>
                    No Kafka Integrations available
                  </SelectOption>
                )}
              </SelectList>
            </SynSelect>
          )}
        </SynFormField>
        <FormFieldError id={errorId} message={integrationError} />
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
      <StackItem>
        <Content component={ContentVariants.p}>
          Integration validation:{' '}
          {staleSelection
            ? 'Selected Integration is unavailable. Select another Integration.'
            : (selected?.validation_status ?? 'Unknown')}
          . This describes the managed connection, not the selected runtime credential’s access.
        </Content>
      </StackItem>
    </Stack>
  )
}
