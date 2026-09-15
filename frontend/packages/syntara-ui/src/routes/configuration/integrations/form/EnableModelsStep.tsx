import {
  Button,
  Content,
  ContentVariants,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  Stack,
  StackItem,
  Title,
} from '@patternfly/react-core'
import { WrenchIcon } from '@patternfly/react-icons'
import { Tbody, Th, Thead, Tr } from '@patternfly/react-table'
import type { IntegrationsAPI } from '@syntara/contracts'
import { useCallback, useMemo, useState } from 'react'

import { FilterBar } from '../../../../components/filters/FilterBar'
import { SynPanelContentStack } from '../../../../components/layout/SynPanelContentStack'
import { SynEmptyStateFilter } from '../../../../components/states/SynEmptyStateFilter'
import { SynEmptyStateNoData } from '../../../../components/states/SynEmptyStateNoData'
import { SynScrollableTableContainer } from '../../../../components/table/SynScrollableTableContainer'
import type { FilterConfig, FilterFieldDefinition } from '../../../../types/filters'
import { getIntegrationNameFilterDefinition } from '../integrationFilters'
import { ModelRow } from '../ModelRow'

import styles from './WizardSteps.module.css'

type DiscoverResult = IntegrationsAPI.components['schemas']['DiscoverResult']
type DiscoveredLLMModel = IntegrationsAPI.components['schemas']['DiscoveredLLMModel']
type InitialModelSelection = IntegrationsAPI.components['schemas']['InitialModelSelection']

/** Props for the wizard-step model selection UI (before the integration is created). */
type EnableModelsStepProps = Readonly<{
  /** Result from the POST /integrations/discover call, or null if not yet tested. */
  testResult: DiscoverResult | null
  /** Currently selected models keyed by model ID. */
  selectedModels: Map<string, InitialModelSelection>
  /** Callback when the selection map changes. */
  onSelectionChange: (models: Map<string, InitialModelSelection>) => void
  /** Triggers a new test-connection request. */
  onTestConnection: () => void
  /** Whether the test-connection button should be disabled (e.g., no credential selected). */
  isTestDisabled: boolean
}>

const modelFilterFieldDefinitions: FilterFieldDefinition[] = [getIntegrationNameFilterDefinition()]

function buildModelEntry(model: DiscoveredLLMModel, isDefault: boolean): InitialModelSelection {
  return {
    model_id: model.id,
    name: model.name,
    description: model.description ?? null,
    enabled: true,
    is_default: isDefault,
  }
}

function EnableModelsStep({
  testResult,
  selectedModels,
  onSelectionChange,
  onTestConnection,
  isTestDisabled,
}: EnableModelsStepProps) {
  const [filters, setFilters] = useState<FilterConfig[]>([])
  const filterValue = useMemo(() => {
    const nameFilter = filters.find((f) => f.key === 'name')
    return typeof nameFilter?.value === 'string' ? nameFilter.value : ''
  }, [filters])
  const hasActiveFilters = filters.length > 0
  const handleClearAllFilters = useCallback(() => setFilters([]), [])

  const models: DiscoveredLLMModel[] = useMemo(
    () => [...(testResult?.discovered_models ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [testResult]
  )

  const filteredModels = useMemo(() => {
    if (!filterValue) return models
    const lower = filterValue.toLowerCase()
    return models.filter((m) => m.name.toLowerCase().includes(lower))
  }, [models, filterValue])

  const allFilteredSelected = filteredModels.length > 0 && filteredModels.every((m) => selectedModels.has(m.id))

  function handleSelectAll() {
    const next = new Map(selectedModels)
    if (allFilteredSelected) {
      for (const model of filteredModels) {
        next.delete(model.id)
      }
    } else {
      for (const model of filteredModels) {
        if (!next.has(model.id)) {
          next.set(model.id, buildModelEntry(model, false))
        }
      }
    }
    onSelectionChange(next)
  }

  function handleSelectRow(modelId: string, checked: boolean) {
    const next = new Map(selectedModels)
    if (!checked) {
      next.delete(modelId)
    } else {
      const model = models.find((m) => m.id === modelId)
      if (model) {
        next.set(model.id, buildModelEntry(model, false))
      }
    }
    onSelectionChange(next)
  }

  function handleSetDefault(modelId: string) {
    const next = new Map(selectedModels)
    for (const [id, entry] of next) {
      if (entry.is_default) {
        next.set(id, { ...entry, is_default: false })
      }
    }
    const target = next.get(modelId)
    if (target) {
      next.set(modelId, { ...target, is_default: true })
    }
    onSelectionChange(next)
  }

  function handleRemoveDefault(modelId: string) {
    const next = new Map(selectedModels)
    const target = next.get(modelId)
    if (target) {
      next.set(modelId, { ...target, is_default: false })
    }
    onSelectionChange(next)
  }

  if (!testResult) {
    return (
      <EmptyState headingLevel="h2" icon={WrenchIcon} titleText="No models discovered yet" isFullHeight>
        <EmptyStateBody>
          Test the connection in the previous step to discover available models, or test it from here.
        </EmptyStateBody>
        {onTestConnection && (
          <EmptyStateFooter>
            <EmptyStateActions>
              <Button
                variant="primary"
                onClick={isTestDisabled ? undefined : onTestConnection}
                isAriaDisabled={isTestDisabled}
              >
                Test connection
              </Button>
            </EmptyStateActions>
          </EmptyStateFooter>
        )}
      </EmptyState>
    )
  }

  if (!testResult.success) {
    return (
      <EmptyState headingLevel="h2" titleText="Connection test failed" status="danger" isFullHeight>
        <EmptyStateBody>{testResult.error ?? 'Unable to connect to the integration.'}</EmptyStateBody>
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button variant="primary" onClick={onTestConnection}>
              Retry connection
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      </EmptyState>
    )
  }

  if (models.length === 0) {
    return (
      <SynEmptyStateNoData
        title="No models found"
        description="The connection was successful, but no models were found on this provider."
      />
    )
  }

  return (
    <SynPanelContentStack className={styles.stepContainerMinWidth}>
      <StackItem>
        <FilterBar
          fieldDefinitions={modelFilterFieldDefinitions}
          filters={filters}
          onFilterChange={setFilters}
          clearAllFilters={handleClearAllFilters}
        />
      </StackItem>

      {hasActiveFilters && filteredModels.length === 0 ? (
        <SynEmptyStateFilter clearAllFilters={handleClearAllFilters} />
      ) : (
        <SynScrollableTableContainer caption="Enable models">
          <colgroup>
            <col className={styles.checkboxCol} />
            <col />
            <col className={styles.kebabCol} />
          </colgroup>
          <Thead>
            <Tr>
              <Th
                select={{
                  onSelect: handleSelectAll,
                  isSelected: allFilteredSelected,
                }}
                screenReaderText="Select all models"
              />
              <Th>Name</Th>
              <Th screenReaderText="Actions" />
            </Tr>
          </Thead>
          <Tbody>
            {filteredModels.map((model, index) => {
              const entry = selectedModels.get(model.id)
              const isEnabled = entry !== undefined
              const isDefault = entry?.is_default === true

              return (
                <ModelRow
                  key={model.id}
                  model={model}
                  index={index}
                  isEnabled={isEnabled}
                  isDefault={isDefault}
                  onSelect={handleSelectRow}
                  onSetDefault={handleSetDefault}
                  onRemoveDefault={handleRemoveDefault}
                />
              )
            })}
          </Tbody>
        </SynScrollableTableContainer>
      )}
    </SynPanelContentStack>
  )
}

export type EnableModelsWrapperProps = EnableModelsStepProps

export function EnableModelsWrapper({
  testResult,
  selectedModels,
  onSelectionChange,
  onTestConnection,
  isTestDisabled,
}: EnableModelsWrapperProps) {
  const hasModels = testResult?.success && (testResult.discovered_models?.length ?? 0) > 0

  return (
    <Stack className={styles.stepContainer}>
      {hasModels && (
        <StackItem>
          <Title headingLevel="h2" size="lg" className={styles.stepTitle}>
            Enable models
          </Title>
          <Content component={ContentVariants.p} className={styles.stepDescription}>
            Select which models to enable for this LLM provider and set one as the default. Use the row menu to mark a
            default model. You can change this later.
          </Content>
        </StackItem>
      )}
      <StackItem isFilled className={styles.fillContent}>
        <EnableModelsStep
          testResult={testResult}
          selectedModels={selectedModels}
          onSelectionChange={onSelectionChange}
          onTestConnection={onTestConnection}
          isTestDisabled={isTestDisabled}
        />
      </StackItem>
    </Stack>
  )
}
