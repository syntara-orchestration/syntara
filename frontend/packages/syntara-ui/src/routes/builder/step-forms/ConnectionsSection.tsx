import {
  ActionList,
  ActionListItem,
  Button,
  Content,
  ContentVariants,
  Divider,
  ExpandableSection,
  Flex,
  FlexItem,
  Icon,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiWarningFillIcon } from '@patternfly/react-icons'
import { Fragment, useMemo, useState } from 'react'

import { CREDENTIAL_TYPES_BY_INTEGRATION } from '../../configuration/integrations/integrationFilters'
import { CredentialSelector } from '../components/CredentialSelector'

import styles from './ConnectionsSection.module.css'
import { AI_INTEGRATION_CONNECTIONS_HELP } from './shared/stepFieldHelpText'
import type { IntegrationWithTools, ToolSelection } from './ToolsMultiSelect'

export type IntegrationConnection = {
  integration_id: string
  credential_id: string
}

export type ConnectionsSectionProps = {
  integrations: IntegrationWithTools[]
  toolSelection: ToolSelection
  integrationConnections: IntegrationConnection[]
  onConnectionChange: (connections: IntegrationConnection[]) => void
  projectId?: string
}

type IntegrationRow = {
  integration: IntegrationWithTools
  toolCount: number
  connection: IntegrationConnection | undefined
}

function buildIntegrationRows(
  integrations: IntegrationWithTools[],
  toolSelection: ToolSelection,
  integrationConnections: IntegrationConnection[]
): IntegrationRow[] {
  const connectionMap = new Map(integrationConnections.map((c) => [c.integration_id, c]))

  if (toolSelection.strategy === 'NONE') return []

  if (toolSelection.strategy === 'ALL') {
    return integrations
      .filter((integration) => integration.discovered_tools.length > 0)
      .map((integration) => ({
        integration,
        toolCount: integration.discovered_tools.length,
        connection: connectionMap.get(integration.id),
      }))
  }

  // SELECTED
  const selectionSet = new Set(toolSelection.toolIds)
  return integrations
    .filter((integration) => integration.discovered_tools.some((t) => selectionSet.has(t.id)))
    .map((integration) => ({
      integration,
      toolCount: integration.discovered_tools.filter((t) => selectionSet.has(t.id)).length,
      connection: connectionMap.get(integration.id),
    }))
}

type IntegrationConnectionRowProps = {
  row: IntegrationRow
  isExpanded: boolean
  onExpand: () => void
  onCollapse: () => void
  onCredentialChange: (credentialId: string | undefined) => void
  projectId?: string
}

function IntegrationConnectionRow({
  row,
  isExpanded,
  onExpand,
  onCollapse,
  onCredentialChange,
  projectId,
}: Readonly<IntegrationConnectionRowProps>) {
  const { integration, toolCount, connection } = row

  const handleCredentialSelect = (credentialId: string | undefined) => {
    onCredentialChange(credentialId)
    onCollapse()
  }

  const handleRemove = () => {
    onCredentialChange(undefined)
    onCollapse()
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <Flex alignItems={{ default: 'alignItemsCenter' }} justifyContent={{ default: 'justifyContentSpaceBetween' }}>
          <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
            <FlexItem>
              {connection ? (
                <Icon status="success" aria-hidden>
                  <RhUiCheckCircleIcon />
                </Icon>
              ) : (
                <Icon status="warning" aria-hidden>
                  <RhUiWarningFillIcon />
                </Icon>
              )}
            </FlexItem>
            <FlexItem>
              <strong>{integration.name}</strong>
            </FlexItem>
            <FlexItem>
              <Content component={ContentVariants.small} className={styles.dimmed}>
                {String(toolCount)} tool{toolCount !== 1 ? 's' : ''}
              </Content>
            </FlexItem>
          </Flex>
          {!isExpanded && (
            <FlexItem>
              <Button variant="link" size="sm" onClick={onExpand}>
                {connection ? 'Change' : 'Set up connection'}{' '}
                <span className="pf-v6-u-screen-reader">
                  {connection ? 'credential for' : 'for'} {integration.name}
                </span>
              </Button>
            </FlexItem>
          )}
        </Flex>
      </StackItem>
      {isExpanded && (
        <>
          <StackItem>
            <CredentialSelector
              value={connection?.credential_id}
              onChange={handleCredentialSelect}
              compatibleTypeNames={CREDENTIAL_TYPES_BY_INTEGRATION.mcp_server}
              label={`Execution credential for ${integration.name}`}
              fieldId={`mcp-credential-${integration.id}`}
              placeholder="Select execution credential"
              helpText={AI_INTEGRATION_CONNECTIONS_HELP}
              allowCreate
              projectId={projectId}
            />
          </StackItem>
          <StackItem>
            <ActionList isIconList>
              {connection && (
                <ActionListItem>
                  <Button variant="link" isDanger onClick={handleRemove}>
                    Remove <span className="pf-v6-u-screen-reader">credential for {integration.name}</span>
                  </Button>
                </ActionListItem>
              )}
              <ActionListItem>
                <Button variant="link" onClick={onCollapse}>
                  Cancel <span className="pf-v6-u-screen-reader">setting up connection for {integration.name}</span>
                </Button>
              </ActionListItem>
            </ActionList>
          </StackItem>
        </>
      )}
    </Stack>
  )
}

/**
 * Shows which integrations need execution credentials based on the tool selections.
 * Each integration row is collapsed by default; clicking "Set up connection" or
 * "Change" expands that row to reveal the CredentialSelector. Only one row can
 * be expanded at a time.
 */
export function ConnectionsSection({
  integrations,
  toolSelection,
  integrationConnections,
  onConnectionChange,
  projectId,
}: Readonly<ConnectionsSectionProps>) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [sectionExpanded, setSectionExpanded] = useState(true)

  const rows = useMemo(
    () => buildIntegrationRows(integrations, toolSelection, integrationConnections),
    [integrations, toolSelection, integrationConnections]
  )

  const connectedCount = useMemo(() => rows.filter((r) => r.connection !== undefined).length, [rows])

  if (rows.length === 0) return null

  const handleCredentialChange = (integrationId: string, credentialId: string | undefined) => {
    if (credentialId) {
      const existing = integrationConnections.filter((c) => c.integration_id !== integrationId)
      onConnectionChange([...existing, { integration_id: integrationId, credential_id: credentialId }])
    } else {
      onConnectionChange(integrationConnections.filter((c) => c.integration_id !== integrationId))
    }
  }

  const toggleContent = (
    <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
      <FlexItem>
        <strong>Connections</strong>
      </FlexItem>
      <FlexItem>
        <Content component={ContentVariants.small} className={styles.dimmed}>
          {String(connectedCount)} of {String(rows.length)} connected
        </Content>
      </FlexItem>
    </Flex>
  )

  return (
    <div className={styles.sectionClip}>
      <ExpandableSection
        isExpanded={sectionExpanded}
        onToggle={(_event, val) => setSectionExpanded(val)}
        isIndented
        toggleContent={toggleContent}
      >
        {rows.map((row, index) => (
          <Fragment key={row.integration.id}>
            {index > 0 && <Divider />}
            <div className={styles.connectionRow}>
              <IntegrationConnectionRow
                row={row}
                isExpanded={expandedId === row.integration.id}
                onExpand={() => setExpandedId(row.integration.id)}
                onCollapse={() => setExpandedId(null)}
                onCredentialChange={(credentialId) => handleCredentialChange(row.integration.id, credentialId)}
                projectId={projectId}
              />
            </div>
          </Fragment>
        ))}
      </ExpandableSection>
    </div>
  )
}
