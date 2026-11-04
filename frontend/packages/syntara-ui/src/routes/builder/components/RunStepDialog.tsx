import {
  Alert,
  Button,
  Content,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { ExecutionsAPI } from '@syntara/contracts'
import { useState, useCallback, useRef, useEffect } from 'react'

import { workflowFetchClient } from '../../../client'
import { FlowNodeType } from '../../../constants'
import { useBlurOnOpen } from '../../../hooks/useBlurOnOpen'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { schemaToTemplateData } from '../../../utils/jsonSchemaTemplate'
import { handleToV2Port } from '../utils/edgeHelpers'

import { ExpandableCodeEditor } from './ExpandableCodeEditor'

type TestExecutionCreate = ExecutionsAPI.components['schemas']['TestExecutionCreate']
type TestExecutionResponse = {
  id: string
}

type PredecessorNode = Readonly<{
  id: string
  name: string
  type?: string
  portTowardTarget?: string
  isTrigger?: boolean
}>

const CONTROL_FLOW_TYPES = new Set<string>([
  FlowNodeType.CONDITION,
  FlowNodeType.LOOP,
  FlowNodeType.APPROVAL,
  FlowNodeType.FORM_PROMPT,
])

export type RunStepDialogData = {
  nodeId: string
  nodeName: string
  predecessors: PredecessorNode[]
}

export type RunStepExecutionCreatedOptions = {
  clearMocksOnComplete: boolean
}

type RunStepDialogProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  onExecutionCreated?: (executionId: string, options: RunStepExecutionCreatedOptions) => void
  nodeId: string | null
  nodeName: string
  workflowId: string
  predecessors?: PredecessorNode[]
  pinnedMockData?: Record<string, Record<string, unknown>>
  triggerInputSchema?: Record<string, unknown>
  triggerNodeId?: string
}>

// Brief success state before auto-close per UX spec
const SUCCESS_AUTO_CLOSE_DELAY_MS = 800

type DialogView = 'choice' | 'mock-editor'
type RunState = 'idle' | 'running' | 'success' | 'error'

function getMockEditorDescription(predecessors: readonly PredecessorNode[], nodeName: string): string {
  if (predecessors.length === 1) {
    return `Provide mock output data for the previous step (${predecessors[0].name}). This data will be used as input for ${nodeName}, and only ${nodeName} will execute.`
  }
  return `Provide mock output data for the previous steps. This data will be applied to all ${predecessors.length} predecessor steps, and only ${nodeName} will execute.`
}

function buildTriggerMockJson(
  triggerInputSchema: Record<string, unknown>,
  predecessors: readonly PredecessorNode[],
  pinnedMockData: Record<string, Record<string, unknown>> | undefined
): string {
  const triggerTemplate = schemaToTemplateData(triggerInputSchema)
  const nonTriggerPreds = predecessors.filter((p) => !p.isTrigger)
  if (nonTriggerPreds.length === 0) return JSON.stringify(triggerTemplate, null, 2)

  const keyed: Record<string, Record<string, unknown>> = {}
  for (const pred of predecessors) {
    keyed[pred.id] = pred.isTrigger ? triggerTemplate : (pinnedMockData?.[pred.id] ?? {})
  }
  return JSON.stringify(keyed, null, 2)
}

function buildPinnedMockJson(
  pinnedMockData: Record<string, Record<string, unknown>>,
  predecessors: readonly PredecessorNode[]
): string {
  const entries = Object.entries(pinnedMockData)
  if (entries.length === 0) return ''
  if (predecessors.length === 1 && entries.length === 1) return JSON.stringify(entries[0][1], null, 2)
  const keyed: Record<string, Record<string, unknown>> = {}
  for (const pred of predecessors) {
    if (pinnedMockData[pred.id]) keyed[pred.id] = pinnedMockData[pred.id]
  }
  return JSON.stringify(keyed, null, 2)
}

function getInitialMockJson(
  pinnedMockData: Record<string, Record<string, unknown>> | undefined,
  predecessors: readonly PredecessorNode[],
  triggerInputSchema?: Record<string, unknown>
): string {
  const hasTrigger =
    triggerInputSchema && Object.keys(triggerInputSchema).length > 0 && predecessors.some((p) => p.isTrigger)
  if (hasTrigger) return buildTriggerMockJson(triggerInputSchema, predecessors, pinnedMockData)
  if (!pinnedMockData) return ''
  return buildPinnedMockJson(pinnedMockData, predecessors)
}

function isKeyedByPredecessors(parsed: Record<string, unknown>, predecessors: readonly PredecessorNode[]): boolean {
  const predIds = new Set(predecessors.map((p) => p.id))
  return Object.keys(parsed).length > 0 && Object.keys(parsed).every((key) => predIds.has(key))
}

type PreResolvedEntry = { output: Record<string, unknown>; control?: { next_port: string } }

function buildControlData(pred: PredecessorNode): { next_port: string } | undefined {
  if (!pred.type || !CONTROL_FLOW_TYPES.has(pred.type) || !pred.portTowardTarget) return undefined
  return { next_port: handleToV2Port(pred.portTowardTarget) ?? pred.portTowardTarget }
}

type MockSubmission = {
  preResolvedNodes: TestExecutionCreate['pre_resolved_nodes']
  triggerInputs: Record<string, unknown>
}

function buildPreResolvedEntry(pred: PredecessorNode, output: Record<string, unknown>): PreResolvedEntry {
  const entry: PreResolvedEntry = { output }
  const control = buildControlData(pred)
  if (control) entry.control = control
  return entry
}

function buildNoTriggerSubmission(
  parsedMock: Record<string, unknown>,
  predecessors: readonly PredecessorNode[]
): MockSubmission {
  const preResolvedNodes: TestExecutionCreate['pre_resolved_nodes'] = {}
  const keyed = predecessors.length > 1 && isKeyedByPredecessors(parsedMock, predecessors)
  for (const pred of predecessors) {
    const output = keyed ? ((parsedMock[pred.id] as Record<string, unknown>) ?? {}) : parsedMock
    preResolvedNodes[pred.id] = buildPreResolvedEntry(pred, output)
  }
  return { preResolvedNodes, triggerInputs: {} }
}

function buildMixedSubmission(
  parsedMock: Record<string, unknown>,
  predecessors: readonly PredecessorNode[]
): MockSubmission {
  const triggerPreds = predecessors.filter((p) => p.isTrigger)
  const nonTriggerPreds = predecessors.filter((p) => !p.isTrigger)

  if (!isKeyedByPredecessors(parsedMock, predecessors)) {
    const preResolvedNodes: TestExecutionCreate['pre_resolved_nodes'] = {}
    for (const pred of nonTriggerPreds) preResolvedNodes[pred.id] = { output: {} }
    return { preResolvedNodes, triggerInputs: parsedMock }
  }

  const preResolvedNodes: TestExecutionCreate['pre_resolved_nodes'] = {}
  let triggerInputs: Record<string, unknown> = {}
  for (const pred of triggerPreds) {
    triggerInputs = { ...triggerInputs, ...((parsedMock[pred.id] as Record<string, unknown>) ?? {}) }
  }
  for (const pred of nonTriggerPreds) {
    preResolvedNodes[pred.id] = buildPreResolvedEntry(pred, (parsedMock[pred.id] as Record<string, unknown>) ?? {})
  }
  return { preResolvedNodes, triggerInputs }
}

function buildMockSubmission(
  parsedMock: Record<string, unknown>,
  predecessors: readonly PredecessorNode[]
): MockSubmission {
  const hasTrigger = predecessors.some((p) => p.isTrigger)
  if (!hasTrigger) return buildNoTriggerSubmission(parsedMock, predecessors)
  const hasNonTrigger = predecessors.some((p) => !p.isTrigger)
  if (!hasNonTrigger) return { preResolvedNodes: {}, triggerInputs: parsedMock }
  return buildMixedSubmission(parsedMock, predecessors)
}

type ChoiceViewProps = Readonly<{
  isOpen: boolean
  handleClose: () => void
  nodeName: string
  runState: RunState
  runError: string | null
  setRunState: (state: RunState) => void
  setRunError: (error: string | null) => void
  handleRunAllPrevious: () => void
  handleSetMockData: () => void
  hasPinnedData: boolean
  hasPredecessors: boolean
}>

function ChoiceView({
  isOpen,
  handleClose,
  nodeName,
  runState,
  runError,
  setRunState,
  setRunError,
  handleRunAllPrevious,
  handleSetMockData,
  hasPinnedData,
  hasPredecessors,
}: ChoiceViewProps) {
  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium" aria-labelledby="run-step-choice-title">
      <ModalHeader title={`Run ${nodeName}?`} labelId="run-step-choice-title" />
      <ModalBody>
        <Stack hasGutter>
          <StackItem>
            <Content component="p">
              You are about to run this step manually. Run all previous steps up to this one, or set mock output for
              previous steps so only this step runs.
            </Content>
          </StackItem>
          {runState === 'error' && runError && (
            <StackItem>
              <Alert variant="danger" isInline title="Failed to start execution">
                <Content component="p">{runError}</Content>
              </Alert>
            </StackItem>
          )}
        </Stack>
      </ModalBody>
      <ModalFooter>
        {runState === 'error' ? (
          <Button
            variant="primary"
            onClick={() => {
              setRunState('idle')
              setRunError(null)
            }}
          >
            Retry
          </Button>
        ) : (
          <>
            <Button
              variant="primary"
              onClick={handleRunAllPrevious}
              isDisabled={runState !== 'idle'}
              isLoading={runState === 'running'}
            >
              {runState === 'running' ? 'Running...' : 'Run all previous steps'}
            </Button>
            <Button
              variant="secondary"
              onClick={handleSetMockData}
              isDisabled={runState !== 'idle' || !hasPredecessors}
            >
              {hasPinnedData ? 'Use mock data' : 'Set mock data'}
            </Button>
          </>
        )}
        <Button variant="link" onClick={handleClose} isDisabled={runState === 'running'}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}

type MockEditorViewProps = Readonly<{
  isOpen: boolean
  handleClose: () => void
  nodeName: string
  predecessors: readonly PredecessorNode[]
  mockJson: string
  setMockJson: (json: string) => void
  jsonError: string | null
  setJsonError: (error: string | null) => void
  runState: RunState
  runError: string | null
  setRunState: (state: RunState) => void
  setRunError: (error: string | null) => void
  handleRunWithMockData: () => Promise<void>
}>

function MockEditorView({
  isOpen,
  handleClose,
  nodeName,
  predecessors,
  mockJson,
  setMockJson,
  jsonError,
  setJsonError,
  runState,
  runError,
  setRunState,
  setRunError,
  handleRunWithMockData,
}: MockEditorViewProps) {
  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="large" aria-labelledby="run-step-mock-title">
      <ModalHeader title={`Set mock data for ${nodeName}`} labelId="run-step-mock-title" />
      <ModalBody>
        <Stack hasGutter>
          <StackItem>
            <Content component="p">{getMockEditorDescription(predecessors, nodeName)}</Content>
          </StackItem>
          <StackItem>
            <ExpandableCodeEditor
              code={mockJson}
              onCodeChange={(value) => {
                setMockJson(value)
                setJsonError(null)
              }}
              language="json"
              height="15rem"
              modalTitle={`Mock output data for ${nodeName}`}
              ariaLabel="Mock JSON output data"
              isReadOnly={runState !== 'idle'}
            />
            {jsonError && <Alert variant="danger" isInline isPlain title={jsonError} />}
          </StackItem>
          {runState === 'success' && (
            <StackItem>
              <Alert variant="success" isInline title="Execution started successfully" />
            </StackItem>
          )}
          {runState === 'error' && runError && (
            <StackItem>
              <Alert variant="danger" isInline title="Failed to start execution">
                <Content component="p">{runError}</Content>
              </Alert>
            </StackItem>
          )}
        </Stack>
      </ModalBody>
      <ModalFooter>
        {runState === 'error' ? (
          <Button
            variant="primary"
            onClick={() => {
              setRunState('idle')
              setRunError(null)
            }}
          >
            Retry
          </Button>
        ) : (
          <Button
            variant="primary"
            onClick={() => detachPromise(handleRunWithMockData())}
            isDisabled={runState !== 'idle'}
            isLoading={runState === 'running'}
          >
            {runState === 'running' ? 'Running...' : 'Run'}
          </Button>
        )}
        <Button variant="link" onClick={handleClose} isDisabled={runState === 'running'}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}

export function RunStepDialog({
  isOpen,
  onClose,
  onExecutionCreated,
  nodeId,
  nodeName,
  workflowId,
  predecessors = [],
  pinnedMockData,
  triggerInputSchema,
  triggerNodeId,
}: RunStepDialogProps) {
  useBlurOnOpen(isOpen)
  const [dialogView, setDialogView] = useState<DialogView>('choice')
  const [mockJson, setMockJson] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [runState, setRunState] = useState<RunState>('idle')
  const [runError, setRunError] = useState<string | null>(null)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const clearMocksRef = useRef(false)

  useEffect(() => {
    return () => {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current)
    }
  }, [])

  const handleClose = useCallback(() => {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current)
    clearMocksRef.current = false
    setDialogView('choice')
    setMockJson('')
    setJsonError(null)
    setRunState('idle')
    setRunError(null)
    onClose()
  }, [onClose])

  const handleSetMockData = useCallback(() => {
    setMockJson(getInitialMockJson(pinnedMockData, predecessors, triggerInputSchema))
    setDialogView('mock-editor')
  }, [pinnedMockData, predecessors, triggerInputSchema])

  const executeTestRun = useCallback(
    async (submission: MockSubmission) => {
      if (!nodeId || !workflowId) return
      if (runState !== 'idle') return

      setRunState('running')
      setRunError(null)

      try {
        const { data, error } = await workflowFetchClient.POST(
          '/workflows/{workflow_id}/test' as never,
          {
            params: { path: { workflow_id: workflowId } },
            body: {
              target_node_id: nodeId,
              pre_resolved_nodes: submission.preResolvedNodes,
              trigger_inputs: submission.triggerInputs,
              execute_target: true,
              trigger_node_id: triggerNodeId ?? '',
            } satisfies TestExecutionCreate,
          } as never
        )

        if (error) {
          setRunState('error')
          setRunError(getErrorMessage(error))
          return
        }

        setRunState('success')

        const responseData = data as TestExecutionResponse | undefined
        if (responseData?.id && onExecutionCreated) {
          onExecutionCreated(responseData.id, { clearMocksOnComplete: clearMocksRef.current })
        }

        closeTimerRef.current = setTimeout(handleClose, SUCCESS_AUTO_CLOSE_DELAY_MS)
      } catch (err) {
        setRunState('error')
        setRunError(getErrorMessage(err))
      }
    },
    [nodeId, workflowId, handleClose, onExecutionCreated, runState, triggerNodeId]
  )

  const handleRunAllPrevious = useCallback(() => {
    clearMocksRef.current = true
    detachPromise(executeTestRun({ preResolvedNodes: {}, triggerInputs: {} }))
  }, [executeTestRun])

  const handleRunWithMockData = useCallback(async () => {
    let parsedMock: Record<string, unknown> = {}
    if (mockJson.trim()) {
      try {
        parsedMock = JSON.parse(mockJson) as Record<string, unknown>
        setJsonError(null)
      } catch (error) {
        setJsonError(error instanceof Error ? error.message : 'Invalid JSON')
        return
      }
    }

    clearMocksRef.current = false
    await executeTestRun(buildMockSubmission(parsedMock, predecessors))
  }, [mockJson, predecessors, executeTestRun])

  const hasPinnedData = pinnedMockData && Object.keys(pinnedMockData).length > 0

  if (dialogView === 'choice') {
    return (
      <ChoiceView
        isOpen={isOpen}
        handleClose={handleClose}
        nodeName={nodeName}
        runState={runState}
        runError={runError}
        setRunState={setRunState}
        setRunError={setRunError}
        handleRunAllPrevious={handleRunAllPrevious}
        handleSetMockData={handleSetMockData}
        hasPinnedData={!!hasPinnedData}
        hasPredecessors={predecessors.length > 0}
      />
    )
  }

  return (
    <MockEditorView
      isOpen={isOpen}
      handleClose={handleClose}
      nodeName={nodeName}
      predecessors={predecessors}
      mockJson={mockJson}
      setMockJson={setMockJson}
      jsonError={jsonError}
      setJsonError={setJsonError}
      runState={runState}
      runError={runError}
      setRunState={setRunState}
      setRunError={setRunError}
      handleRunWithMockData={handleRunWithMockData}
    />
  )
}
