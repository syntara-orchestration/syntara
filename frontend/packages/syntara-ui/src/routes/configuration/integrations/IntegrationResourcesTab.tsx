import {
  Button,
  Content,
  ContentVariants,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  SearchInput,
  StackItem,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
} from '@patternfly/react-core'
import { RhUiSyncIcon, RhUiWarningIcon } from '@patternfly/react-icons'
import { Thead, Tbody, Tr, Th, Td } from '@patternfly/react-table'
import type { IntegrationsAPI, Tool } from '@syntara/contracts'
import { useMemo, useState } from 'react'

import { integrationsClient } from '../../../client'
import { NxLabel } from '../../../components/labels/NxLabel'
import { SynPageBody } from '../../../components/layout/SynPage'
import { NxEmptyStateNoData } from '../../../components/states/NxEmptyStateNoData'
import { NxScrollableTableContainer } from '../../../components/table/NxScrollableTableContainer'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { formatTimeAgo } from '../../../utils/dateUtils'
import { detachPromise } from '../../../utils/detachPromise'

import styles from './IntegrationDetail.module.css'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

type IntegrationResourcesTabProps = Readonly<{
  integrationId: string
  tools: Tool[]
  enabledToolIds: Set<string>
  enabledCount: number
  handleSelectTool: (toolId: string, checked: boolean) => void
  lastRefreshedAt: string | null | undefined
  canUpdate: boolean
  onRefreshed: () => Promise<IntegrationRead | undefined>
  refetchTools: () => Promise<unknown>
}>

export function IntegrationResourcesTab({
  integrationId,
  tools,
  enabledToolIds,
  enabledCount,
  handleSelectTool,
  lastRefreshedAt,
  canUpdate,
  onRefreshed,
  refetchTools,
}: IntegrationResourcesTabProps) {
  const { showAlert } = useAlerts()
  const [nameFilter, setNameFilter] = useState('')

  const filteredTools = useMemo(() => {
    if (!nameFilter) return tools
    const lower = nameFilter.toLowerCase()
    return tools.filter(
      (t) => (t.name ?? '').toLowerCase().includes(lower) || (t.description ?? '').toLowerCase().includes(lower)
    )
  }, [tools, nameFilter])

  const missingCount = tools.filter((t) => t.status === 'missing').length
  const allSelected = filteredTools.length > 0 && filteredTools.every((t) => enabledToolIds.has(t.id))

  function handleSelectAll(checked: boolean) {
    for (const tool of filteredTools) {
      handleSelectTool(tool.id, checked)
    }
  }

  const { mutateAsync: refreshIntegrationAsync, isPending: isRefreshing } = integrationsClient.useMutation(
    'post',
    '/integrations/{integration_id}/refresh'
  )

  async function handleRefresh() {
    try {
      await refreshIntegrationAsync({ params: { path: { integration_id: integrationId } } })
      const updated = await onRefreshed()
      detachPromise(refetchTools())
      if (updated?.refresh_status === 'error') {
        showAlert({
          title: 'Refresh failed',
          description: updated.refresh_error ?? 'Failed to refresh resources.',
          variant: 'danger',
          autoDismiss: true,
        })
      } else {
        showAlert({
          title: 'Resources refreshed',
          description: 'Resources have been refreshed successfully.',
          variant: 'success',
          autoDismiss: true,
        })
      }
    } catch (error: unknown) {
      showAlert({
        title: 'Refresh failed',
        description: `Failed to refresh resources: ${getErrorMessage(error)}`,
        variant: 'danger',
        autoDismiss: true,
      })
    }
  }

  if (tools.length === 0) {
    return (
      <SynPageBody isCentered>
        <NxEmptyStateNoData
          title="No resources discovered yet"
          description="Click Refresh tools to discover available tools from this integration."
          buttonText="Refresh tools"
          addData={canUpdate ? () => detachPromise(handleRefresh()) : undefined}
        />
      </SynPageBody>
    )
  }

  return (
    <>
      <StackItem>
        <Toolbar>
          <ToolbarContent alignItems="center">
            <ToolbarItem>
              <SearchInput
                aria-label="Filter tools by name"
                placeholder="Filter tools by name"
                value={nameFilter}
                onChange={(_event, value) => setNameFilter(value)}
                onClear={() => setNameFilter('')}
              />
            </ToolbarItem>
            <ToolbarItem>
              <Content component={ContentVariants.small}>
                {enabledCount} of {tools.length} enabled
              </Content>
            </ToolbarItem>
            <ToolbarItem>
              <Button
                variant="plain"
                aria-label="Refresh resources"
                icon={<RhUiSyncIcon />}
                isLoading={isRefreshing}
                isAriaDisabled={!canUpdate || isRefreshing}
                onClick={canUpdate ? () => detachPromise(handleRefresh()) : undefined}
              />
            </ToolbarItem>
            <ToolbarItem>
              <Content component={ContentVariants.small}>Last refreshed: {formatTimeAgo(lastRefreshedAt)}</Content>
            </ToolbarItem>
            {missingCount > 0 && (
              <ToolbarItem>
                <NxLabel variant="outline" status="warning" icon={<RhUiWarningIcon />}>
                  {missingCount} not found
                </NxLabel>
              </ToolbarItem>
            )}
          </ToolbarContent>
        </Toolbar>
      </StackItem>

      <NxScrollableTableContainer aria-label="tools table" caption="Integration tools">
        <colgroup>
          <col className={styles.checkboxCol} />
          <col />
        </colgroup>
        <Thead>
          <Tr>
            <Th
              select={{
                onSelect: (_event, isSelecting) => handleSelectAll(isSelecting),
                isSelected: allSelected,
                isHeaderSelectDisabled: !canUpdate || filteredTools.length === 0,
                isDisabled: !canUpdate || filteredTools.length === 0,
              }}
              screenReaderText="Select all tools"
            />
            <Th>Name</Th>
          </Tr>
        </Thead>
        <Tbody>
          {filteredTools.map((tool, index) => (
            <Tr key={tool.id}>
              <Td
                select={{
                  rowIndex: index,
                  onSelect: (_event, isSelecting) => handleSelectTool(tool.id, isSelecting),
                  isSelected: enabledToolIds.has(tool.id),
                  isDisabled: !canUpdate,
                }}
              />
              <Td dataLabel="Name">
                <div className={styles.nameCell}>
                  <DescriptionList>
                    <DescriptionListGroup>
                      <DescriptionListTerm>{tool.name}</DescriptionListTerm>
                      <DescriptionListDescription>{tool.description}</DescriptionListDescription>
                    </DescriptionListGroup>
                  </DescriptionList>
                  {tool.status === 'missing' && (
                    <NxLabel
                      variant="outline"
                      status="warning"
                      icon={<RhUiWarningIcon />}
                      className={styles.notFoundLabel}
                    >
                      Not found
                    </NxLabel>
                  )}
                </div>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </NxScrollableTableContainer>
    </>
  )
}
