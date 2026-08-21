import {
  Dropdown,
  DropdownItem,
  DropdownList,
  ExpandableSection,
  Flex,
  FlexItem,
  Label,
  MenuToggle,
  SearchInput,
  Stack,
  StackItem,
  Title,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiCloseIcon } from '@patternfly/react-icons'
import { useMemo, useState } from 'react'

import { SynPageBody } from '../../../components/layout/SynPage'
import { SynPanel } from '../../../components/layout/SynPanel'
import { useMockDataStore } from '../../../stores/useMockDataStore'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { selectActivities, selectTriggers } from '../../../stores/workflowStoreSelectors'
import { parseTriggerIndex } from '../../../utils/triggerNodeIds'
import type { WorkflowMetadata } from '../types/workflowMetadata'
import { useIsVersionView } from '../VersionViewContext'

import { useUpstreamNodes, type UpstreamNodeInfo } from './hooks/useUpstreamNodes'
import { InputEmptyState } from './InputEmptyState'
import { InputNodeContent, InputPanelNodeSection } from './InputNodeContent'
import { MockDataEditor } from './MockDataEditor'
import styles from './panels.module.css'
import { getUpstreamNodeDisplayName } from './utils/getUpstreamNodeDisplayName'
import { buildMockJsonSkeleton } from './utils/mockDataUtils'
import { getTriggerInputSchemaFields } from './utils/triggerSchemaUtils'
import { VariablesAndContextTree } from './VariablesAndContextTree'
import { ViewToggle, type PanelView } from './ViewToggle'

type InputPanelProps = {
  nodeId: string
  executionData?: Record<string, Record<string, unknown>> | null
  sourceNodeId?: string | null
  workflowMetadata?: WorkflowMetadata
  workflowId?: string | null
  onRunPreviousSteps?: () => void
}

/** Compute the effective upstream nodes, falling back to source ancestors when direct upstream is empty. */
function computeEffectiveUpstream(
  upstreamNodes: UpstreamNodeInfo[],
  sourceNodeId: string | null | undefined,
  sourceAncestors: UpstreamNodeInfo[],
  activities: { id: string; name?: string; type: string }[] | undefined,
  triggers: { id: string; name?: string; type: string }[] | undefined
): UpstreamNodeInfo[] {
  if (upstreamNodes.length > 0) return upstreamNodes
  if (!sourceNodeId) return []

  const activity = activities?.find((a) => a.id === sourceNodeId)
  if (activity) {
    return [{ id: activity.id, name: activity.name ?? activity.id, type: activity.type }, ...sourceAncestors]
  }

  const trigger = triggers?.find((t) => t.id === sourceNodeId)
  if (trigger) {
    return [{ id: trigger.id, name: trigger.name ?? trigger.id, type: trigger.type }, ...sourceAncestors]
  }

  const triggerIndex = parseTriggerIndex(sourceNodeId)
  if (triggerIndex !== undefined && triggers?.[triggerIndex]) {
    const resolved = triggers[triggerIndex]
    return [{ id: resolved.id, name: resolved.name ?? resolved.id, type: resolved.type }, ...sourceAncestors]
  }

  return []
}

/**
 * Merge three data sources into a single input map. Precedence (highest wins):
 * 1. Real execution data (base layer, kept when present)
 * 2. Pinned output mocks from upstream nodes (fill gaps not covered by execution data)
 * 3. Input mocks for the current node (fill remaining gaps, highest precedence)
 */
function computeMergedExecutionData(
  executionData: Record<string, Record<string, unknown>> | null | undefined,
  effectiveUpstream: UpstreamNodeInfo[],
  nodeInputMocks: Record<string, Record<string, unknown>> | undefined,
  upstreamOutputMocks: Record<string, Record<string, unknown>>
): Record<string, Record<string, unknown>> | null {
  const merged = { ...executionData }
  for (const upstream of effectiveUpstream) {
    const upstreamOutputMock = upstreamOutputMocks[upstream.id]
    if (upstreamOutputMock && !merged[upstream.id]) {
      merged[upstream.id] = upstreamOutputMock
    }
  }
  if (nodeInputMocks) {
    for (const [predId, mockData] of Object.entries(nodeInputMocks)) {
      if (!merged[predId]) {
        merged[predId] = mockData
      }
    }
  }
  return Object.keys(merged).length > 0 ? merged : null
}

function getInputMockSkeleton(
  predecessorId: string,
  effectiveUpstream: UpstreamNodeInfo[],
  triggers: { id: string; parameters?: Record<string, unknown> }[] | undefined
): string {
  const node = effectiveUpstream.find((n) => n.id === predecessorId)
  if (!node) return '{}'
  return buildMockJsonSkeleton(node.type, getTriggerInputSchemaFields(predecessorId, triggers))
}

/** Track which upstream node sections are expanded, syncing when the upstream set changes. */
function useExpandedSections(effectiveUpstream: UpstreamNodeInfo[]) {
  const upstreamIdsSerialized = effectiveUpstream.map((n) => n.id).join(',')

  const [state, setState] = useState(() => ({
    prevIds: upstreamIdsSerialized,
    sections: Object.fromEntries(effectiveUpstream.map((node, index) => [node.id, index === 0])),
  }))

  let { sections } = state
  if (state.prevIds !== upstreamIdsSerialized) {
    const ids = upstreamIdsSerialized.split(',').filter(Boolean)
    const updated: Record<string, boolean> = {}
    ids.forEach((id, index) => {
      updated[id] = state.sections[id] ?? index === 0
    })
    sections = updated
    setState({ prevIds: upstreamIdsSerialized, sections: updated })
  }

  const setExpandedSections = (
    updater: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)
  ) => {
    setState((prev) => {
      const newSections = typeof updater === 'function' ? updater(prev.sections) : updater
      return { ...prev, sections: newSections }
    })
  }

  return [sections, setExpandedSections] as const
}

type InputPanelMockControlsProps = {
  hasUpstream: boolean
  inputMockCount: number
  isSetMockDropdownOpen: boolean
  setIsSetMockDropdownOpen: (open: boolean) => void
  isUnpinDropdownOpen: boolean
  setIsUnpinDropdownOpen: (open: boolean) => void
  effectiveUpstream: UpstreamNodeInfo[]
  handleSetMockData: (predecessorId: string) => void
  handleUnpinSingle: (predecessorId: string) => void
  unpinAllInputMocks: (nodeId: string) => void
  hasInputMock: (nodeId: string, predecessorId: string) => boolean
  nodeId: string
}

function InputPanelMockControls({
  hasUpstream,
  inputMockCount,
  isSetMockDropdownOpen,
  setIsSetMockDropdownOpen,
  isUnpinDropdownOpen,
  setIsUnpinDropdownOpen,
  effectiveUpstream,
  handleSetMockData,
  handleUnpinSingle,
  unpinAllInputMocks,
  hasInputMock,
  nodeId,
}: Readonly<InputPanelMockControlsProps>) {
  if (!hasUpstream) return null

  return (
    <StackItem>
      <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
        {inputMockCount > 0 && (
          <FlexItem>
            <Label color="grey" isCompact>
              Mock data pinned ({inputMockCount})
            </Label>
          </FlexItem>
        )}
        <FlexItem>
          <Dropdown
            isOpen={isSetMockDropdownOpen}
            onOpenChange={setIsSetMockDropdownOpen}
            toggle={(toggleRef) => (
              <MenuToggle
                ref={toggleRef}
                variant="plainText"
                icon={<RhUiAddIcon />}
                onClick={() => setIsSetMockDropdownOpen(!isSetMockDropdownOpen)}
                className={styles.linkToggle}
              >
                Set mock data
              </MenuToggle>
            )}
          >
            <DropdownList>
              {effectiveUpstream.map((node) => (
                <DropdownItem key={node.id} onClick={() => handleSetMockData(node.id)}>
                  {getUpstreamNodeDisplayName(node)}
                </DropdownItem>
              ))}
            </DropdownList>
          </Dropdown>
        </FlexItem>
        {inputMockCount > 0 && (
          <FlexItem>
            <Dropdown
              isOpen={isUnpinDropdownOpen}
              onOpenChange={setIsUnpinDropdownOpen}
              toggle={(toggleRef) => (
                <MenuToggle
                  ref={toggleRef}
                  variant="plainText"
                  onClick={() => setIsUnpinDropdownOpen(!isUnpinDropdownOpen)}
                  icon={<RhUiCloseIcon />}
                  className={styles.dangerToggle}
                >
                  Unpin data
                </MenuToggle>
              )}
            >
              <DropdownList>
                {effectiveUpstream
                  .filter((node) => hasInputMock(nodeId, node.id))
                  .map((node) => (
                    <DropdownItem
                      key={node.id}
                      onClick={() => {
                        handleUnpinSingle(node.id)
                        setIsUnpinDropdownOpen(false)
                      }}
                    >
                      {getUpstreamNodeDisplayName(node)}
                    </DropdownItem>
                  ))}
                <DropdownItem isDanger onClick={() => unpinAllInputMocks(nodeId)}>
                  Unpin all
                </DropdownItem>
              </DropdownList>
            </Dropdown>
          </FlexItem>
        )}
      </Flex>
    </StackItem>
  )
}

export function InputPanel({
  nodeId,
  executionData,
  sourceNodeId,
  workflowMetadata,
  workflowId,
  onRunPreviousSteps,
}: Readonly<InputPanelProps>) {
  const upstreamNodes = useUpstreamNodes(nodeId)
  const sourceAncestors = useUpstreamNodes(sourceNodeId ?? '')
  const activities = useWorkflowStore(selectActivities)
  const triggers = useWorkflowStore(selectTriggers)

  const effectiveUpstream = useMemo(
    () => computeEffectiveUpstream(upstreamNodes, sourceNodeId, sourceAncestors, activities, triggers),
    [upstreamNodes, sourceNodeId, sourceAncestors, activities, triggers]
  )

  const hasUpstream = effectiveUpstream.length > 0

  const [activeView, setActiveView] = useState<PanelView>('schema')
  const [searchTerm, setSearchTerm] = useState('')
  const [expandedSections, setExpandedSections] = useExpandedSections(effectiveUpstream)
  const [isVarsSectionExpanded, setIsVarsSectionExpanded] = useState(false)

  const [editingPredecessorId, setEditingPredecessorId] = useState<string | null>(null)
  const [isSetMockDropdownOpen, setIsSetMockDropdownOpen] = useState(false)
  const [isUnpinDropdownOpen, setIsUnpinDropdownOpen] = useState(false)

  const pinInputMock = useMockDataStore((s) => s.pinInputMock)
  const unpinInputMock = useMockDataStore((s) => s.unpinInputMock)
  const unpinAllInputMocks = useMockDataStore((s) => s.unpinAllInputMocks)
  const hasInputMock = useMockDataStore((s) => s.hasInputMock)
  const inputMockCount = useMockDataStore((s) => s.getInputMockCount(nodeId))

  const nodeInputMocks = useMockDataStore((s) => s.pinnedData[nodeId]?.inputMocks)
  const pinnedData = useMockDataStore((s) => s.pinnedData)

  const upstreamOutputMocks = useMemo(() => {
    const result: Record<string, Record<string, unknown>> = {}
    for (const upstream of effectiveUpstream) {
      const mock = pinnedData[upstream.id]?.outputMock
      if (mock) result[upstream.id] = mock
    }
    return result
  }, [pinnedData, effectiveUpstream])

  const mergedExecutionData = useMemo(
    () => computeMergedExecutionData(executionData, effectiveUpstream, nodeInputMocks, upstreamOutputMocks),
    [executionData, effectiveUpstream, nodeInputMocks, upstreamOutputMocks]
  )

  const isVersionView = useIsVersionView()

  const hasData = hasUpstream && mergedExecutionData != null && Object.keys(mergedExecutionData).length > 0

  function handleSetMockData(predecessorId: string) {
    setEditingPredecessorId(predecessorId)
    setIsSetMockDropdownOpen(false)
  }

  function handleUnpinSingle(predecessorId: string) {
    unpinInputMock(nodeId, predecessorId)
  }

  if (editingPredecessorId) {
    const editingNode = effectiveUpstream.find((n) => n.id === editingPredecessorId)
    const existingMock = nodeInputMocks?.[editingPredecessorId]
    const executionOrUpstreamData = mergedExecutionData?.[editingPredecessorId]
    const dataToStringify = existingMock ?? executionOrUpstreamData
    const initialJson = dataToStringify
      ? JSON.stringify(dataToStringify, null, 2)
      : getInputMockSkeleton(editingPredecessorId, effectiveUpstream, triggers)

    return (
      <MockDataEditor
        predecessorName={getUpstreamNodeDisplayName(editingNode ?? { id: editingPredecessorId, type: 'unknown' })}
        initialJson={initialJson}
        onPin={(parsed) => {
          pinInputMock(nodeId, editingPredecessorId, parsed)
          setEditingPredecessorId(null)
        }}
        onCancel={() => setEditingPredecessorId(null)}
      />
    )
  }

  return (
    <SynPanel
      variant="raised"
      isFullHeight
      className={styles.panelContainer}
      panelMainProps={{ className: styles.panelMain }}
      panelMainBodyProps={{ className: styles.panelBodyFlex }}
    >
      <Stack hasGutter className={styles.fillMinHeight}>
        {/* Row 1: Title, search, and view toggle */}
        <StackItem>
          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
            <FlexItem>
              <Title headingLevel="h2" size="md">
                Input
              </Title>
            </FlexItem>
            {hasData && (
              <>
                <FlexItem flex={{ default: 'flex_1' }}>
                  <SearchInput
                    placeholder="Search fields"
                    value={searchTerm}
                    onChange={(_event, value) => setSearchTerm(value)}
                    onClear={() => setSearchTerm('')}
                    aria-label="Search input fields"
                  />
                </FlexItem>
                <FlexItem>
                  <ViewToggle activeView={activeView} onChange={setActiveView} ariaLabel="Input view selection" />
                </FlexItem>
              </>
            )}
          </Flex>
        </StackItem>

        {/* Row 2: Mock data controls (only when hasUpstream, hidden in version view) */}
        {!isVersionView && (
          <InputPanelMockControls
            hasUpstream={hasUpstream}
            inputMockCount={inputMockCount}
            isSetMockDropdownOpen={isSetMockDropdownOpen}
            setIsSetMockDropdownOpen={setIsSetMockDropdownOpen}
            isUnpinDropdownOpen={isUnpinDropdownOpen}
            setIsUnpinDropdownOpen={setIsUnpinDropdownOpen}
            effectiveUpstream={effectiveUpstream}
            handleSetMockData={handleSetMockData}
            handleUnpinSingle={handleUnpinSingle}
            unpinAllInputMocks={unpinAllInputMocks}
            hasInputMock={hasInputMock}
            nodeId={nodeId}
          />
        )}
        {!hasUpstream && (
          <StackItem>
            <InputEmptyState variant="not-connected" />
          </StackItem>
        )}
        {hasUpstream && (
          <StackItem isFilled className={styles.filledMinHeight}>
            <SynPageBody className={styles.scrollableContent}>
              {effectiveUpstream.map((upstreamNode) => {
                const isExpanded = expandedSections[upstreamNode.id] ?? false
                const hasPinnedMock = hasInputMock(nodeId, upstreamNode.id)

                return (
                  <ExpandableSection
                    key={upstreamNode.id}
                    toggleText={getUpstreamNodeDisplayName(upstreamNode)}
                    isIndented
                    isExpanded={isExpanded}
                    onToggle={(_event, expanded) =>
                      setExpandedSections((prev) => ({ ...prev, [upstreamNode.id]: expanded }))
                    }
                    className={styles.sectionToggleText}
                  >
                    <InputPanelNodeSection
                      upstreamNode={upstreamNode}
                      hasPinnedMock={hasPinnedMock}
                      handleUnpinSingle={handleUnpinSingle}
                    >
                      <InputNodeContent
                        upstreamNode={upstreamNode}
                        hasData={hasData}
                        mergedExecutionData={mergedExecutionData}
                        triggers={triggers}
                        activeView={activeView}
                        searchTerm={searchTerm}
                        onRunPreviousSteps={onRunPreviousSteps}
                        workflowId={workflowId}
                      />
                    </InputPanelNodeSection>
                  </ExpandableSection>
                )
              })}
              <ExpandableSection
                toggleText="Variables and context"
                isIndented
                isExpanded={isVarsSectionExpanded}
                onToggle={(_event, expanded) => setIsVarsSectionExpanded(expanded)}
                className={styles.sectionToggleText}
              >
                <VariablesAndContextTree workflowMetadata={workflowMetadata} />
              </ExpandableSection>
            </SynPageBody>
          </StackItem>
        )}
      </Stack>
    </SynPanel>
  )
}
