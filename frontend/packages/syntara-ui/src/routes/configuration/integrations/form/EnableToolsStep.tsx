import {
  Button,
  Content,
  ContentVariants,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  SearchInput,
  Stack,
  StackItem,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
} from '@patternfly/react-core'
import { WrenchIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IntegrationsAPI } from '@syntara/contracts'
import { useMemo, useState } from 'react'

import { SynPanelContentStack } from '../../../../components/layout/SynPanelContentStack'
import { NxEmptyStateNoData } from '../../../../components/states/NxEmptyStateNoData'
import { NxScrollableTableContainer } from '../../../../components/table/NxScrollableTableContainer'

import styles from './WizardSteps.module.css'

type DiscoverResult = IntegrationsAPI.components['schemas']['DiscoverResult']
type DiscoveredTool = IntegrationsAPI.components['schemas']['DiscoveredTool']

type EnableToolsStepProps = Readonly<{
  testResult: DiscoverResult | null
  selectedNames: Set<string>
  onSelectionChange: (selectedNames: Set<string>) => void
  onTestConnection?: () => void
  isTestDisabled?: boolean
}>

function EnableToolsStep({
  testResult,
  selectedNames,
  onSelectionChange,
  onTestConnection,
  isTestDisabled,
}: EnableToolsStepProps) {
  const [filterValue, setFilterValue] = useState('')
  const tools: DiscoveredTool[] = useMemo(() => testResult?.discovered_tools ?? [], [testResult])

  const filteredTools = useMemo(() => {
    if (!filterValue) return tools
    const lower = filterValue.toLowerCase()
    return tools.filter((t) => t.name.toLowerCase().includes(lower))
  }, [tools, filterValue])

  const allSelected = filteredTools.length > 0 && filteredTools.every((t) => selectedNames.has(t.name))

  function handleSelectAll() {
    if (allSelected) {
      const filteredSet = new Set(filteredTools.map((t) => t.name))
      const next = new Set(selectedNames)
      for (const name of filteredSet) next.delete(name)
      onSelectionChange(next)
    } else {
      const next = new Set(selectedNames)
      for (const t of filteredTools) next.add(t.name)
      onSelectionChange(next)
    }
  }

  function handleSelectRow(toolName: string) {
    const next = new Set(selectedNames)
    if (next.has(toolName)) {
      next.delete(toolName)
    } else {
      next.add(toolName)
    }
    onSelectionChange(next)
  }

  if (!testResult) {
    return (
      <EmptyState headingLevel="h3" icon={WrenchIcon} titleText="No tools discovered yet" isFullHeight>
        <EmptyStateBody>
          Test the connection in the previous step to discover available tools, or test it from here.
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
      <EmptyState headingLevel="h3" titleText="Connection test failed" status="danger" isFullHeight>
        <EmptyStateBody>{testResult.error ?? 'Unable to connect to the integration.'}</EmptyStateBody>
        {onTestConnection && (
          <EmptyStateFooter>
            <EmptyStateActions>
              <Button variant="primary" onClick={onTestConnection}>
                Retry connection
              </Button>
            </EmptyStateActions>
          </EmptyStateFooter>
        )}
      </EmptyState>
    )
  }

  if (tools.length === 0) {
    return (
      <NxEmptyStateNoData
        title="No tools found"
        description="The connection was successful, but no tools were found on this server."
      />
    )
  }

  return (
    <SynPanelContentStack className={styles.stepContainerMinWidth}>
      <StackItem>
        <Toolbar>
          <ToolbarContent>
            <ToolbarItem>
              <SearchInput
                aria-label="Filter by name"
                placeholder="Filter by name"
                value={filterValue}
                onChange={(_event, value) => setFilterValue(value)}
                onClear={() => setFilterValue('')}
              />
            </ToolbarItem>
          </ToolbarContent>
        </Toolbar>
      </StackItem>

      <NxScrollableTableContainer caption="Enable tools">
        <colgroup>
          <col className={styles.checkboxCol} />
          <col />
        </colgroup>
        <Thead>
          <Tr>
            <Th
              select={{
                onSelect: handleSelectAll,
                isSelected: allSelected,
              }}
            />
            <Th>Name</Th>
          </Tr>
        </Thead>
        <Tbody>
          {filteredTools.map((tool, index) => (
            <Tr key={tool.name}>
              <Td
                select={{
                  rowIndex: index,
                  onSelect: () => handleSelectRow(tool.name),
                  isSelected: selectedNames.has(tool.name),
                }}
              />
              <Td dataLabel="Name">
                <DescriptionList>
                  <DescriptionListGroup>
                    <DescriptionListTerm>{tool.name}</DescriptionListTerm>
                    <DescriptionListDescription>{tool.description ?? 'No description'}</DescriptionListDescription>
                  </DescriptionListGroup>
                </DescriptionList>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </NxScrollableTableContainer>
    </SynPanelContentStack>
  )
}

type EnableToolsWrapperProps = Readonly<{
  testResult: DiscoverResult | null
  selectedNames: Set<string>
  onSelectionChange: (selectedNames: Set<string>) => void
  onTestConnection?: () => void
  isTestDisabled?: boolean
}>

export function EnableToolsWrapper({
  testResult,
  selectedNames,
  onSelectionChange,
  onTestConnection,
  isTestDisabled,
}: EnableToolsWrapperProps) {
  const hasTools = testResult?.success && (testResult.discovered_tools?.length ?? 0) > 0

  return (
    <Stack className={styles.stepContainer}>
      {hasTools && (
        <StackItem>
          <Content component="h2" className={styles.stepTitle}>
            Enable tools
          </Content>
          <Content component={ContentVariants.p} className={styles.stepDescription}>
            Select which tools to enable for this integration. You can change this later.
          </Content>
        </StackItem>
      )}
      <StackItem isFilled className={styles.fillContent}>
        <EnableToolsStep
          testResult={testResult}
          selectedNames={selectedNames}
          onSelectionChange={onSelectionChange}
          onTestConnection={onTestConnection}
          isTestDisabled={isTestDisabled}
        />
      </StackItem>
    </Stack>
  )
}
