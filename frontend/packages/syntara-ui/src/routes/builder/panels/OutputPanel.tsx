import {
  Button,
  EmptyState,
  EmptyStateBody,
  Flex,
  FlexItem,
  Label,
  Stack,
  StackItem,
  Title,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiCloseIcon } from '@patternfly/react-icons'
import { useMemo, useState } from 'react'

import { SynPanel } from '../../../components/layout/SynPanel'
import { useMockDataStore } from '../../../stores/useMockDataStore'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { selectActivities } from '../../../stores/workflowStoreSelectors'
import { useIsVersionView } from '../VersionViewContext'

import { InlineMockEditor } from './InlineMockEditor'
import styles from './panels.module.css'
import { buildMockJsonSkeleton, parseJsonObject } from './utils/mockDataUtils'
import { OutputJsonView } from './views/OutputJsonView'
import { OutputSchemaView } from './views/OutputSchemaView'
import { OutputTableView } from './views/OutputTableView'
import { ViewToggle, type PanelView } from './ViewToggle'

type OutputPanelProps = {
  outputData?: Record<string, unknown> | null
  nodeId: string
}

export function OutputPanel({ outputData, nodeId }: Readonly<OutputPanelProps>) {
  const isVersionView = useIsVersionView()
  const [activeView, setActiveView] = useState<PanelView>('json')
  const [isEditing, setIsEditing] = useState(false)
  const [mockJsonText, setMockJsonText] = useState('{\n\n}')
  const [jsonError, setJsonError] = useState<string | null>(null)

  const pinOutputMock = useMockDataStore((s) => s.pinOutputMock)
  const unpinOutputMock = useMockDataStore((s) => s.unpinOutputMock)
  const outputMock = useMockDataStore((s) => s.getOutputMock(nodeId))
  const activities = useWorkflowStore(selectActivities)

  const nodeType = useMemo(() => {
    const activity = activities?.find((a) => a.id === nodeId)
    return activity?.type ?? null
  }, [activities, nodeId])

  // Priority: real execution data > mock data > empty
  const displayData = outputData ?? outputMock

  function buildOutputSkeleton(): string {
    // Best case: use existing execution output as the template
    if (outputData) {
      return JSON.stringify(outputData, null, 2)
    }

    // Fallback: use the node type's output schema
    const skeleton = buildMockJsonSkeleton(nodeType, null)
    return skeleton !== '{}' ? skeleton : '{\n\n}'
  }

  function handleSetMockData() {
    // If already pinned, pre-populate with existing data
    const existingMock = useMockDataStore.getState().getOutputMock(nodeId)
    const initialJson = existingMock ? JSON.stringify(existingMock, null, 2) : buildOutputSkeleton()
    setMockJsonText(initialJson)
    setJsonError(null)
    setIsEditing(true)
  }

  function handlePinData() {
    const result = parseJsonObject(mockJsonText)
    if (!result.success) {
      setJsonError(result.error)
      return
    }
    pinOutputMock(nodeId, result.data)
    setIsEditing(false)
    setJsonError(null)
  }

  function handleCancel() {
    setIsEditing(false)
    setJsonError(null)
  }

  function handleUnpinData() {
    unpinOutputMock(nodeId)
  }

  function renderView() {
    if (!displayData) return null

    switch (activeView) {
      case 'schema':
        return <OutputSchemaView data={displayData} />
      case 'table':
        return <OutputTableView data={displayData} />
      case 'json':
        return <OutputJsonView data={displayData} />
      default: {
        const _exhaustive: never = activeView
        return _exhaustive
      }
    }
  }

  return (
    <SynPanel
      variant="raised"
      isFullHeight
      className={styles.panelContainer}
      panelMainProps={{ className: styles.panelMain }}
      panelMainBodyProps={{ className: styles.panelBody }}
    >
      <Stack hasGutter className={styles.fillMinHeight}>
        {/* Row 1: Title, search, and view toggle — matches Input panel layout */}
        <StackItem>
          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
            <FlexItem>
              <Title headingLevel="h2" size="md">
                Output
              </Title>
            </FlexItem>
            {displayData && !isEditing && (
              <FlexItem>
                <ViewToggle activeView={activeView} onChange={setActiveView} ariaLabel="Output view selection" />
              </FlexItem>
            )}
          </Flex>
        </StackItem>

        {/* Row 2: Mock data controls — Set mock data first, Unpin data second (hidden in version view) */}
        {!isVersionView && !isEditing && (
          <StackItem>
            <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
              {outputMock && (
                <FlexItem>
                  <Label color="grey" isCompact>
                    Mock data pinned
                  </Label>
                </FlexItem>
              )}
              <FlexItem>
                <Button variant="link" icon={<RhUiAddIcon />} onClick={handleSetMockData} className={styles.linkToggle}>
                  Set mock data
                </Button>
              </FlexItem>
              {outputMock && (
                <FlexItem>
                  <Button variant="link" isDanger onClick={handleUnpinData} className={styles.dangerToggle}>
                    <RhUiCloseIcon /> Unpin data
                  </Button>
                </FlexItem>
              )}
            </Flex>
          </StackItem>
        )}

        {/* Content area */}
        {isEditing && (
          <InlineMockEditor
            code={mockJsonText}
            onCodeChange={setMockJsonText}
            onPin={handlePinData}
            onCancel={handleCancel}
            jsonError={jsonError}
          />
        )}
        {!isEditing && displayData && (
          <StackItem isFilled className={styles.scrollableContent}>
            {renderView()}
          </StackItem>
        )}
        {!isEditing && !displayData && (
          <EmptyState headingLevel="h3" titleText="No output data" variant="xs">
            <EmptyStateBody>Run the workflow or test this step to see output data here.</EmptyStateBody>
          </EmptyState>
        )}
      </Stack>
    </SynPanel>
  )
}
