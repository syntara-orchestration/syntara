import { Truncate } from '@patternfly/react-core'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IntegrationsAPI } from '@syntara/contracts'
import { useCallback, useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { integrationsClient } from '../../../client'
import { SynPanelContentStack } from '../../../components/layout/SynPanelContentStack'
import { SynListPanelTable, SynListPanelView } from '../../../components/panels/list/SynListPanel'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import { LinkCell } from '../../../components/table/LinkCell'
import { UserTimestamp } from '../../../components/table/UserTimestamp'
import { useExpandableRowIds } from '../../../hooks/useExpandableRowIds'
import { detachPromise } from '../../../utils/detachPromise'
import { INTEGRATION_TYPE_LABELS } from '../integrations/integrationFilters'
import { StatusLabel } from '../integrations/StatusLabel'

import { expandableRowIds, hasTrimmedDescription, relatedResourceRowId } from './credentialRelatedTableUtils'
import { DescriptionExpandableContent } from './DescriptionExpandableContent'

type Integration = IntegrationsAPI.components['schemas']['IntegrationRead']

type CredentialIntegrationsTabProps = {
  credentialId: string
}

const INTEGRATION_COLUMN_COUNT = 6
const noop = () => {}

function integrationHref(integrationId: string): string {
  return AppRoute.Configuration.Integrations.Detail.replace(':integrationId', integrationId)
}

function integrationScopeLabel(scope: Integration['scope']): string {
  return scope === 'project' ? 'Project' : 'Global'
}

function IntegrationsTable({
  integrations,
  expandedRows,
  allRowsExpanded,
  onToggleRow,
  onCollapseAll,
}: Readonly<{
  integrations: Integration[]
  expandedRows: Set<string>
  allRowsExpanded: boolean
  onToggleRow: (id: string) => void
  onCollapseAll: () => void
}>) {
  return (
    <>
      <Thead>
        <Tr>
          <Th
            expand={{
              areAllExpanded: allRowsExpanded,
              collapseAllAriaLabel: allRowsExpanded ? 'Collapse all' : 'Expand all',
              onToggle: onCollapseAll,
            }}
            aria-label="Row expansion"
          />
          <Th>Integration name</Th>
          <Th>Type</Th>
          <Th>Created by</Th>
          <Th>Status</Th>
          <Th>Scope</Th>
        </Tr>
      </Thead>
      {integrations.map((integration, rowIndex) => {
        const rowId = relatedResourceRowId(integration.id, 'integration', rowIndex)
        const expandable = hasTrimmedDescription(integration.description)
        const isExpanded = expandable && expandedRows.has(rowId)
        return (
          <Tbody key={rowId} isExpanded={isExpanded}>
            <Tr isContentExpanded={isExpanded}>
              <Td
                expand={
                  expandable
                    ? {
                        rowIndex,
                        isExpanded,
                        onToggle: () => onToggleRow(rowId),
                      }
                    : undefined
                }
              />
              <Td dataLabel="Integration name">
                <LinkCell href={integrationHref(integration.id ?? '')}>
                  <Truncate content={integration.name} />
                </LinkCell>
              </Td>
              <Td dataLabel="Type">
                {INTEGRATION_TYPE_LABELS[integration.integration_type ?? ''] ?? integration.integration_type ?? ''}
              </Td>
              <Td dataLabel="Created by">
                <UserTimestamp user={integration.created_by} timestamp={integration.created_at} inline />
              </Td>
              <Td dataLabel="Status">
                <StatusLabel
                  status={integration.validation_status ?? 'unknown'}
                  errorMessage={integration.validation_error}
                />
              </Td>
              <Td dataLabel="Scope">{integrationScopeLabel(integration.scope)}</Td>
            </Tr>
            {expandable && integration.description ? (
              <Tr isExpanded={isExpanded}>
                <Td colSpan={INTEGRATION_COLUMN_COUNT}>
                  <DescriptionExpandableContent description={integration.description} />
                </Td>
              </Tr>
            ) : null}
          </Tbody>
        )
      })}
    </>
  )
}

export function CredentialIntegrationsTab({ credentialId }: Readonly<CredentialIntegrationsTabProps>) {
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const handlePerPageChange = useCallback((newPerPage: number) => {
    setPerPage(newPerPage)
    setPage(1)
  }, [])

  const query = integrationsClient.useQuery('get', '/integrations', {
    params: { query: { management_credential_id: credentialId } },
  })
  const integrations = query.data?.resources ?? []
  const paginatedIntegrations = integrations.slice((page - 1) * perPage, page * perPage)
  const expandableIds = useMemo(() => expandableRowIds(paginatedIntegrations, 'integration'), [paginatedIntegrations])
  const { expandedRows, allRowsExpanded, handleToggleRow, handleCollapseAll } = useExpandableRowIds(expandableIds)

  return (
    <SynPanelContentStack>
      <SynListPanelView
        isPending={query.isPending}
        error={query.error}
        onRetry={() => detachPromise(query.refetch())}
        errorTitle="Failed to load integrations"
        isEmpty={integrations.length === 0}
        hasActiveFilters={false}
        onClearAllFilters={noop}
        noDataState={
          <SynEmptyStateNoData
            title="No integrations yet"
            description="This credential is not currently referenced by any integrations. Integrations will appear here once they are configured to use this credential."
          />
        }
        body={
          <SynListPanelTable
            caption="Integrations using this credential"
            isExpandable
            footer={{
              page,
              perPage,
              total: integrations.length,
              hasNext: page * perPage < integrations.length,
              onPrev: () => setPage((p) => Math.max(1, p - 1)),
              onNext: () => setPage((p) => p + 1),
              onPerPageChange: handlePerPageChange,
            }}
          >
            <IntegrationsTable
              integrations={paginatedIntegrations}
              expandedRows={expandedRows}
              allRowsExpanded={allRowsExpanded}
              onToggleRow={handleToggleRow}
              onCollapseAll={handleCollapseAll}
            />
          </SynListPanelTable>
        }
      />
    </SynPanelContentStack>
  )
}
