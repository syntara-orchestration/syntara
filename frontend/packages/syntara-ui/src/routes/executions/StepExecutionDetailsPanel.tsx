import {
  Button,
  Flex,
  FlexItem,
  Icon,
  Spinner,
  Stack,
  StackItem,
  Tab,
  Tabs,
  TabTitleText,
  Tooltip,
} from '@patternfly/react-core'
import {
  RhUiDislikeFillIcon,
  RhUiEditIcon,
  RhUiExternalLinkIcon,
  RhUiInformationIcon,
  RhUiLikeFillIcon,
  RhUiWarningFillIcon,
} from '@patternfly/react-icons'
import { ActivityTypeEnum } from '@syntara/contracts'
import { useMemo, useState, type ComponentType } from 'react'

import { SynLabel } from '../../components/labels/SynLabel'
import { SynErrorState } from '../../components/states/SynErrorState'
import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { useElapsedTime } from '../../hooks/useElapsedTime'
import { extractAAPJobUrl, isAAPNodeType } from '../../utils/aapJobUrl'
import { capitalize } from '../../utils/capitalize'
import { formatElapsedTime } from '../../utils/dateUtils'
import { detachPromise } from '../../utils/detachPromise'
import type { PanelView } from '../builder/panels/ViewToggle'
import { getRetryActivityMarkers } from '../builder/utils/replayedNodes'
import type { ActivityState } from '../workflows/execution/types'
import { extractApprovalAudit, type ApprovalAudit } from '../workflows/execution/utils/activityState'

import { extractAgentTrace } from './agentTraceTypes'
import { AgentTraceView } from './AgentTraceView'
import { useStepExecutionDetails } from './hooks/useStepExecutionDetails'
import { RetryInputOverrideDetails, type RetryInputOverrideDetailsProps } from './RetryInputOverrideDetails'
import { getEffectiveRetryInputs, getRetryInputEditorValue } from './retryInputOverrides'
import { StepDetailsHeader } from './StepDetailsHeader'
import { StepExecutionDataPane, type IoPaneLayout } from './StepExecutionDataPane'
import styles from './StepExecutionDetailsPanel.module.css'
import { extractUsedTools, type UsedTool } from './utils/extractUsedTools'

type StepExecutionDetailsPanelProps = {
  stepId: string
  stepName: string
  executionId: string
  /** Activity state from the execution store, used for status and elapsed time. */
  stepState?: ActivityState
  /** Step type from workflow definition (e.g. 'aap_job_template'). */
  stepType?: string
  /** Timestamp replayed steps predate; set only for retry executions. */
  replayBaselineAt?: string | null
  retryInputOverride?: Omit<RetryInputOverrideDetailsProps, 'resolvedInputs'>
}

const decisionStatusMap: Record<string, 'success' | 'danger' | 'warning' | 'info'> = {
  approved: 'success',
  rejected: 'danger',
  expired: 'warning',
}

const decisionIconMap: Record<string, ComponentType<{ className?: string }>> = {
  approved: RhUiLikeFillIcon,
  rejected: RhUiDislikeFillIcon,
  expired: RhUiWarningFillIcon,
}

const RETRY_EDIT_BADGE = (
  <SynLabel variant="outline" color="purple" icon={<RhUiInformationIcon />}>
    Edited for retry
  </SynLabel>
)

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
              {capitalize(audit.decision)}
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
  stepType,
}: Readonly<{ outputData: Record<string, unknown> | null; stepType?: string }>) {
  const jobUrl = isAAPNodeType(stepType) ? extractAAPJobUrl(outputData) : null
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

type StepContentAreaProps = Readonly<{
  stepId: string
  inputData: Record<string, unknown> | null
  outputData: Record<string, unknown> | null
  isLoading: boolean
  error: unknown
  refetch: () => Promise<unknown>
  stepIsFailed: boolean
  isAgenticStep: boolean
  activeTab: 'io' | 'agent-steps'
  retryInputOverride?: Omit<RetryInputOverrideDetailsProps, 'resolvedInputs'>
}>

function StepContentArea({
  stepId,
  inputData,
  outputData,
  isLoading,
  error,
  refetch,
  stepIsFailed,
  isAgenticStep,
  activeTab,
  retryInputOverride,
}: StepContentAreaProps) {
  const [inputView, setInputView] = useState<PanelView>('json')
  const [outputView, setOutputView] = useState<PanelView>('json')
  const [paneLayout, setPaneLayout] = useState<IoPaneLayout>('split')
  const effectiveInputData = useMemo(
    () => getEffectiveRetryInputs(inputData, retryInputOverride?.savedOverride),
    [inputData, retryInputOverride?.savedOverride]
  )

  if (error) {
    return (
      <SynErrorState title="Error loading activity data" message={error} onRetry={() => detachPromise(refetch())} />
    )
  }
  if (isLoading) {
    return <Spinner aria-label="Loading activity data" />
  }
  if (activeTab === 'agent-steps' && isAgenticStep) {
    return <AgentTraceView agentTrace={extractAgentTrace(outputData)} />
  }
  const hasSavedRetryOverride = Boolean(
    retryInputOverride?.savedOverride && Object.keys(retryInputOverride.savedOverride).length > 0
  )
  const retryEditorProps = retryInputOverride ? { ...retryInputOverride, resolvedInputs: inputData } : undefined

  if (retryEditorProps?.isEditing) {
    return (
      <div className={styles.retryEditorPane} data-testid="retry-input-override-editor">
        <RetryInputOverrideDetails {...retryEditorProps} />
      </div>
    )
  }

  const showParameters = paneLayout !== 'output'
  const showOutput = paneLayout !== 'parameters'

  return (
    <Flex
      flexWrap={{ default: 'nowrap' }}
      alignItems={{ default: 'alignItemsStretch' }}
      className={styles.dataPaneContainer}
    >
      {showParameters && (
        <FlexItem flex={{ default: 'flex_1' }} className={styles.paneItem}>
          {retryEditorProps ? (
            <div className={styles.retryParametersPane}>
              <StepExecutionDataPane
                title="Input parameters"
                stepId={stepId}
                data={effectiveInputData}
                view={inputView}
                onViewChange={setInputView}
                stackControls
                className={styles.retryParametersViewer}
                titleAddon={hasSavedRetryOverride ? RETRY_EDIT_BADGE : undefined}
                titleAction={
                  retryEditorProps.canEdit ? (
                    <Tooltip content="Edit parameters for retry">
                      <Button
                        variant="plain"
                        aria-label="Edit parameters for retry"
                        isDisabled={retryEditorProps.isDisabled}
                        onClick={() =>
                          retryEditorProps.onEdit(
                            retryEditorProps.target.id,
                            getRetryInputEditorValue(
                              inputData,
                              retryEditorProps.savedOverride,
                              retryEditorProps.target.parameterNames
                            )
                          )
                        }
                        icon={
                          <Icon isInline>
                            <RhUiEditIcon />
                          </Icon>
                        }
                      />
                    </Tooltip>
                  ) : undefined
                }
                paneKey="parameters"
                paneLayout={paneLayout}
                onPaneLayoutChange={setPaneLayout}
              />
              <RetryInputOverrideDetails {...retryEditorProps} />
            </div>
          ) : (
            <StepExecutionDataPane
              title="Parameters"
              stepId={stepId}
              data={inputData}
              view={inputView}
              onViewChange={setInputView}
              paneKey="parameters"
              paneLayout={paneLayout}
              onPaneLayoutChange={setPaneLayout}
            />
          )}
        </FlexItem>
      )}
      {showOutput && (
        <FlexItem flex={{ default: 'flex_1' }} className={styles.paneItem}>
          <StepExecutionDataPane
            title="Output"
            stepId={stepId}
            data={outputData}
            view={outputView}
            onViewChange={setOutputView}
            stackControls={Boolean(retryEditorProps)}
            isErrorState={stepIsFailed}
            paneKey="output"
            paneLayout={paneLayout}
            onPaneLayoutChange={setPaneLayout}
          />
        </FlexItem>
      )}
    </Flex>
  )
}

export function StepExecutionDetailsPanel({
  stepId,
  stepName,
  executionId,
  stepState,
  stepType,
  replayBaselineAt,
  retryInputOverride,
}: Readonly<StepExecutionDetailsPanelProps>) {
  const [activeTab, setActiveTab] = useState<'io' | 'agent-steps'>('io')
  const isAgenticStep = stepType === ActivityTypeEnum.AGENTIC
  const { inputData, outputData, isLoading, error, refetch } = useStepExecutionDetails(
    stepId,
    executionId,
    stepState?.status,
    stepState?.iteration
  )

  const approvalAudit = useMemo(() => extractApprovalAudit(outputData), [outputData])
  const usedTools = useMemo(() => extractUsedTools(outputData), [outputData])

  const stepStarted = stepState?.startedAt ?? null
  const stepCompleted = stepState?.completedAt ?? null
  const stepIsRunning = stepState?.status === 'running'
  const stepIsFailed = stepState?.status === 'failed'
  const { elapsedMs } = useElapsedTime(stepStarted, stepCompleted, stepIsRunning)
  const stepElapsedLabel = elapsedMs === undefined ? undefined : formatElapsedTime(elapsedMs)
  const retryMarkers = getRetryActivityMarkers(stepState, replayBaselineAt, stepType)

  return (
    <Stack className={styles.contentContainer}>
      <StepDetailsHeader
        stepName={stepName}
        stepStarted={stepStarted}
        stepCompleted={stepCompleted}
        stepElapsedLabel={stepElapsedLabel}
        status={stepState?.status}
        nodeType={stepType}
        replayed={retryMarkers.replayed}
        retainedFailure={retryMarkers.retainedFailure}
        triggerInputReused={retryMarkers.triggerInputReused}
      />

      {/* Approval audit strip (shown only for decided approval steps) */}
      {approvalAudit && (
        <StackItem style={{ flexShrink: 0 }}>
          <ApprovalAuditSection audit={approvalAudit} />
        </StackItem>
      )}

      {usedTools && <UsedToolsSection tools={usedTools} />}

      <AAPJobLink outputData={outputData} stepType={stepType} />

      {/* Tab bar for agentic steps */}
      {isAgenticStep && (
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
        <StepContentArea
          key={stepId}
          stepId={stepId}
          inputData={inputData}
          outputData={outputData}
          isLoading={isLoading}
          error={error}
          refetch={refetch}
          stepIsFailed={stepIsFailed}
          isAgenticStep={isAgenticStep}
          activeTab={activeTab}
          retryInputOverride={retryInputOverride}
        />
      </StackItem>
    </Stack>
  )
}
