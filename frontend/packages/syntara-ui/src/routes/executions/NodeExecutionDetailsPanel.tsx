import {
  Content,
  ContentVariants,
  EmptyState,
  EmptyStateBody,
  Flex,
  FlexItem,
  SearchInput,
  Spinner,
  Stack,
  StackItem,
  Tab,
  Tabs,
  TabTitleText,
  Title,
  TitleSizes,
} from '@patternfly/react-core'
import {
  RhUiDislikeFillIcon,
  RhUiExternalLinkIcon,
  RhUiLikeFillIcon,
  RhUiWarningFillIcon,
} from '@patternfly/react-icons'
import { ActivityTypeEnum } from '@syntara/contracts'
import { useEffect, useMemo, useRef, useState } from 'react'

import { NxCodeBlock } from '../../components/details/NxCodeBlock'
import { SynLabel } from '../../components/labels/SynLabel'
import { SynErrorState } from '../../components/states/SynErrorState'
import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { useElapsedTime } from '../../hooks/useElapsedTime'
import { extractAAPJobUrl, isAAPNodeType } from '../../utils/aapJobUrl'
import { formatElapsedTime } from '../../utils/dateUtils'
import { detachPromise } from '../../utils/detachPromise'
import { highlightTextLines } from '../../utils/highlightText'
import { ActivityStatusLabel } from '../builder/ExecutionStatus'
import { InputSchemaView } from '../builder/panels/views/InputSchemaView'
import { InputTableView } from '../builder/panels/views/InputTableView'
import { ViewToggle, type PanelView } from '../builder/panels/ViewToggle'
import type { ActivityState } from '../workflows/execution/types'
import { extractApprovalAudit, type ApprovalAudit } from '../workflows/execution/utils/activityState'

import { extractAgentTrace } from './agentTraceTypes'
import { AgentTraceView } from './AgentTraceView'
import { useNodeExecutionDetails } from './hooks/useNodeExecutionDetails'
import styles from './NodeExecutionDetailsPanel.module.css'
import { extractUsedTools, type UsedTool } from './utils/extractUsedTools'

type NodeExecutionDetailsPanelProps = {
  nodeId: string
  nodeName: string
  executionId: string
  /** Activity state from the execution store, used for status and elapsed time. */
  nodeState?: ActivityState
  /** Node type from workflow definition (e.g. 'aap_job_template'). */
  nodeType?: string
}

function NoDataState({ label }: Readonly<{ label: string }>) {
  return (
    <EmptyState headingLevel="h3" titleText={`No ${label} data`} variant="xs">
      <EmptyStateBody>No {label} data is available for this activity.</EmptyStateBody>
    </EmptyState>
  )
}

type DataPaneProps = {
  title: string
  nodeId: string
  data: Record<string, unknown> | null
  view: PanelView
  onViewChange: (view: PanelView) => void
  isErrorState?: boolean
}

function DataPane({ title, nodeId, data, view, onViewChange, isErrorState = false }: Readonly<DataPaneProps>) {
  const [searchTerm, setSearchTerm] = useState('')
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const jsonText = useMemo(() => (data ? JSON.stringify(data, null, 2) : ''), [data])

  const highlightedJson = useMemo(() => {
    if (!jsonText) return undefined
    return highlightTextLines(jsonText, searchTerm)
  }, [jsonText, searchTerm])

  useEffect(() => {
    if (searchTerm && scrollContainerRef.current) {
      requestAnimationFrame(() => {
        const firstMark = scrollContainerRef.current?.querySelector('mark')
        if (firstMark && typeof firstMark.scrollIntoView === 'function') {
          firstMark.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      })
    }
  }, [searchTerm, view, highlightedJson])

  function renderContent() {
    if (!data) {
      return <NoDataState label={title.toLowerCase()} />
    }
    switch (view) {
      case 'schema':
        return <InputSchemaView data={data} nodeId={nodeId} searchTerm={searchTerm} />
      case 'table':
        return <InputTableView data={data} searchTerm={searchTerm} />
      case 'json':
        return (
          <div style={isErrorState ? { color: 'var(--pf-t--global--color--status--danger--default)' } : undefined}>
            <NxCodeBlock enableCopy enableExpand expandTitle={`${title} JSON`} noMaxHeight copyContent={jsonText}>
              {highlightedJson ?? jsonText}
            </NxCodeBlock>
          </div>
        )
    }
  }

  return (
    <Stack className={styles.contentContainer}>
      <StackItem className={styles.dataPaneHeaderRow}>
        <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }} flexWrap={{ default: 'wrap' }}>
          <FlexItem flex={{ default: 'flexNone' }} className={styles.dataPaneTitle}>
            {title}
          </FlexItem>
          <FlexItem className={styles.dataPaneControlsWrap}>
            <Flex
              alignItems={{ default: 'alignItemsCenter' }}
              gap={{ default: 'gapSm' }}
              flexWrap={{ default: 'wrap' }}
            >
              <FlexItem grow={{ default: 'grow' }} className={styles.searchWrap}>
                <SearchInput
                  aria-label={`Search ${title.toLowerCase()} data`}
                  placeholder="Search"
                  value={searchTerm}
                  onChange={(_event, value) => setSearchTerm(value)}
                  onClear={() => setSearchTerm('')}
                />
              </FlexItem>
              <FlexItem grow={{ default: 'grow' }}>
                <ViewToggle activeView={view} onChange={onViewChange} ariaLabel={`${title} view selection`} />
              </FlexItem>
            </Flex>
          </FlexItem>
        </Flex>
      </StackItem>
      <StackItem isFilled className={styles.scrollPane}>
        <div ref={scrollContainerRef}>{renderContent()}</div>
      </StackItem>
    </Stack>
  )
}

const decisionStatusMap: Record<string, 'success' | 'danger' | 'warning' | 'info'> = {
  approved: 'success',
  rejected: 'danger',
  expired: 'warning',
}

const decisionIconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  approved: RhUiLikeFillIcon,
  rejected: RhUiDislikeFillIcon,
  expired: RhUiWarningFillIcon,
}

function ApprovalAuditSection({ audit }: Readonly<{ audit: ApprovalAudit }>) {
  const status = decisionStatusMap[audit.decision] ?? 'info'
  const IconComponent = decisionIconMap[audit.decision]

  return (
    <Flex className={styles.auditStrip} gap={{ default: 'gapLg' }} alignItems={{ default: 'alignItemsCenter' }}>
      <FlexItem>
        <Stack>
          <StackItem className={styles.auditLabel}>Decision</StackItem>
          <StackItem>
            <SynLabel variant="outline" status={status} icon={IconComponent ? <IconComponent /> : undefined}>
              {audit.decision.charAt(0).toUpperCase() + audit.decision.slice(1)}
            </SynLabel>
          </StackItem>
        </Stack>
      </FlexItem>
      <FlexItem>
        <Stack>
          <StackItem className={styles.auditLabel}>Decided by</StackItem>
          <StackItem className={styles.auditValue}>{audit.decidedBy}</StackItem>
        </Stack>
      </FlexItem>
      <FlexItem>
        <Stack>
          <StackItem className={styles.auditLabel}>Decided at</StackItem>
          <StackItem className={styles.auditValue}>
            <ExecutionTimestamp dateString={audit.decidedAt} />
          </StackItem>
        </Stack>
      </FlexItem>
      {audit.decisionNotes && (
        <FlexItem>
          <Stack>
            <StackItem className={styles.auditLabel}>Notes</StackItem>
            <StackItem className={styles.auditValue}>{audit.decisionNotes}</StackItem>
          </Stack>
        </FlexItem>
      )}
    </Flex>
  )
}

function AAPJobLink({
  outputData,
  nodeType,
}: Readonly<{ outputData: Record<string, unknown> | null; nodeType?: string }>) {
  const jobUrl = isAAPNodeType(nodeType) ? extractAAPJobUrl(outputData) : null
  if (!jobUrl) return null

  return (
    <StackItem style={{ flexShrink: 0, textAlign: 'right', paddingBottom: 'var(--pf-t--global--spacer--xs)' }}>
      <a
        href={jobUrl}
        target="_blank"
        rel="noopener noreferrer"
        style={{ textDecoration: 'underline dotted', textUnderlineOffset: '3px' }}
      >
        View job in AAP <RhUiExternalLinkIcon />
      </a>
    </StackItem>
  )
}

function UsedToolsSection({ tools }: Readonly<{ tools: UsedTool[] }>) {
  return (
    <StackItem className={styles.usedToolsItem}>
      <Flex className={styles.auditStrip} gap={{ default: 'gapLg' }} alignItems={{ default: 'alignItemsCenter' }}>
        <FlexItem>
          <Stack>
            <StackItem className={styles.auditLabel}>Tools used</StackItem>
            <StackItem className={styles.auditValue}>
              {tools.map((tool) => `${tool.name} (${tool.count})`).join(', ')}
            </StackItem>
          </Stack>
        </FlexItem>
      </Flex>
    </StackItem>
  )
}

function NodeDetailsHeader({
  nodeName,
  nodeStarted,
  nodeCompleted,
  nodeElapsedLabel,
  status,
}: Readonly<{
  nodeName: string
  nodeStarted: string | null
  nodeCompleted: string | null
  nodeElapsedLabel?: string
  status?: ActivityState['status']
}>) {
  return (
    <StackItem className={styles.headerRow}>
      <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
        <FlexItem>
          <Title headingLevel="h2" size={TitleSizes.md} style={{ margin: 0 }}>
            {nodeName}
          </Title>
        </FlexItem>
        <FlexItem>
          <Flex gap={{ default: 'gapMd' }} alignItems={{ default: 'alignItemsCenter' }}>
            {nodeStarted && (
              <Content
                component={ContentVariants.small}
                style={{ color: 'var(--pf-t--global--text--color--subtle)', margin: 0 }}
              >
                <ExecutionTimestamp dateString={nodeStarted} />
                {nodeCompleted && (
                  <>
                    {' - '}
                    <ExecutionTimestamp dateString={nodeCompleted} />
                  </>
                )}
              </Content>
            )}
            {nodeElapsedLabel && (
              <Content
                component={ContentVariants.small}
                style={{ color: 'var(--pf-t--global--text--color--subtle)', margin: 0 }}
              >
                Elapsed time: {nodeElapsedLabel}
              </Content>
            )}
            {status && (
              <FlexItem style={{ display: 'flex', alignItems: 'center' }}>
                <ActivityStatusLabel status={status} />
              </FlexItem>
            )}
          </Flex>
        </FlexItem>
      </Flex>
    </StackItem>
  )
}

type NodeContentAreaProps = Readonly<{
  nodeId: string
  inputData: Record<string, unknown> | null
  outputData: Record<string, unknown> | null
  isLoading: boolean
  error: unknown
  refetch: () => Promise<unknown>
  nodeIsFailed: boolean
  isAgenticNode: boolean
  activeTab: 'io' | 'agent-steps'
}>

function NodeContentArea({
  nodeId,
  inputData,
  outputData,
  isLoading,
  error,
  refetch,
  nodeIsFailed,
  isAgenticNode,
  activeTab,
}: NodeContentAreaProps) {
  const [inputView, setInputView] = useState<PanelView>('json')
  const [outputView, setOutputView] = useState<PanelView>('json')

  if (error) {
    return (
      <SynErrorState title="Error loading activity data" message={error} onRetry={() => detachPromise(refetch())} />
    )
  }
  if (isLoading) {
    return <Spinner aria-label="Loading activity data" />
  }
  if (activeTab === 'agent-steps' && isAgenticNode) {
    return <AgentTraceView agentTrace={extractAgentTrace(outputData)} />
  }
  return (
    <Flex
      flexWrap={{ default: 'nowrap' }}
      alignItems={{ default: 'alignItemsStretch' }}
      className={styles.dataPaneContainer}
    >
      <FlexItem flex={{ default: 'flex_1' }} className={styles.paneItem}>
        <DataPane title="Parameters" nodeId={nodeId} data={inputData} view={inputView} onViewChange={setInputView} />
      </FlexItem>
      <FlexItem flex={{ default: 'flex_1' }} className={styles.paneItem}>
        <DataPane
          title="Output"
          nodeId={nodeId}
          data={outputData}
          view={outputView}
          onViewChange={setOutputView}
          isErrorState={nodeIsFailed}
        />
      </FlexItem>
    </Flex>
  )
}

export function NodeExecutionDetailsPanel({
  nodeId,
  nodeName,
  executionId,
  nodeState,
  nodeType,
}: Readonly<NodeExecutionDetailsPanelProps>) {
  const [activeTab, setActiveTab] = useState<'io' | 'agent-steps'>('io')
  const isAgenticNode = nodeType === ActivityTypeEnum.AGENTIC
  const { inputData, outputData, isLoading, error, refetch } = useNodeExecutionDetails(
    nodeId,
    executionId,
    nodeState?.status
  )

  const approvalAudit = useMemo(() => extractApprovalAudit(outputData), [outputData])
  const usedTools = useMemo(() => extractUsedTools(outputData), [outputData])

  const nodeStarted = nodeState?.startedAt ?? null
  const nodeCompleted = nodeState?.completedAt ?? null
  const nodeIsRunning = nodeState?.status === 'running'
  const nodeIsFailed = nodeState?.status === 'failed'
  const { elapsedMs } = useElapsedTime(nodeStarted, nodeCompleted, nodeIsRunning)
  const nodeElapsedLabel = elapsedMs === undefined ? undefined : formatElapsedTime(elapsedMs)

  return (
    <Stack className={styles.contentContainer}>
      <NodeDetailsHeader
        nodeName={nodeName}
        nodeStarted={nodeStarted}
        nodeCompleted={nodeCompleted}
        nodeElapsedLabel={nodeElapsedLabel}
        status={nodeState?.status}
      />

      {/* Approval audit strip (shown only for decided approval nodes) */}
      {approvalAudit && (
        <StackItem style={{ flexShrink: 0 }}>
          <ApprovalAuditSection audit={approvalAudit} />
        </StackItem>
      )}

      {usedTools && <UsedToolsSection tools={usedTools} />}

      <AAPJobLink outputData={outputData} nodeType={nodeType} />

      {/* Tab bar for agentic nodes */}
      {isAgenticNode && (
        <StackItem className={styles.tabBar}>
          <Tabs
            activeKey={activeTab}
            onSelect={(_e, key) => setActiveTab(key as 'io' | 'agent-steps')}
            variant="default"
          >
            <Tab eventKey="io" title={<TabTitleText>Input/Output</TabTitleText>} />
            <Tab eventKey="agent-steps" title={<TabTitleText>Agent steps</TabTitleText>} />
          </Tabs>
        </StackItem>
      )}

      <StackItem isFilled style={{ minHeight: 0, overflow: 'hidden' }}>
        <NodeContentArea
          nodeId={nodeId}
          inputData={inputData}
          outputData={outputData}
          isLoading={isLoading}
          error={error}
          refetch={refetch}
          nodeIsFailed={nodeIsFailed}
          isAgenticNode={isAgenticNode}
          activeTab={activeTab}
        />
      </StackItem>
    </Stack>
  )
}
