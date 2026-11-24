/**
 * Embed Workflow dialog (SDP R12, R15, R16).
 *
 * Select a published workflow in the current project, preview what will be copied
 * (steps, connections, excluded triggers, and any credential/integration references),
 * then insert the copied subgraph into the current workflow as one undoable action.
 *
 * Security (SDP R5): a copied step that references a credential/integration cannot be
 * verified as authorized at copy time, so Embed is BLOCKED for such sources pending the
 * authorization-at-use review — we never silently copy an unauthorized reference, and we
 * introduce no new authorization model.
 */
import {
  Alert,
  Button,
  Content,
  Form,
  FormGroup,
  List,
  ListItem,
  MenuToggle,
  type MenuToggleElement,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  SelectList,
  SelectOption,
  Spinner,
  Stack,
  StackItem,
  Tooltip,
} from '@patternfly/react-core'
import { useRef, useState } from 'react'

import { workflowFetchClient } from '../../../client'
import { SynSelect } from '../../../components/SynSelect'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { useEmbeddableWorkflows } from '../useEmbeddableWorkflows'
import { useEmbedWorkflow } from '../useEmbedWorkflow'
import { copyWorkflowGraph, type CopyWorkflowGraphResult } from '../utils/embed/copyWorkflowGraph'

type EmbedWorkflowDialogProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  projectId?: string
  currentWorkflowId?: string
}>

/** The reason Embed is disabled, for the footer button's tooltip (undefined when it is enabled). */
function getEmbedDisabledReason(state: {
  hasPreview: boolean
  isFetching: boolean
  hasResourceRefs: boolean
  hasSelfReference: boolean
}): string | undefined {
  if (!state.hasPreview) return 'Select a published workflow to embed.'
  if (state.isFetching) return 'Preparing the copy…'
  if (state.hasResourceRefs)
    return 'Resolve the credential or integration references in the source workflow before embedding.'
  if (state.hasSelfReference) return 'This workflow references the workflow you are editing, which would create a loop.'
  return undefined
}

/**
 * Preview body for the selected source: the copy summary plus any blocking (credential /
 * integration, self-reference) or advisory (dangling expression) notices. Kept as its own
 * component so the dialog stays within the project's function size/complexity limits.
 */
function EmbedPreviewBody({
  preview,
  selfReferenceCount,
}: {
  preview: CopyWorkflowGraphResult
  selfReferenceCount: number
}) {
  const stepCount = preview.activities.length
  const connectionCount = preview.edges.length
  const resourceRefs = preview.resourceReferenceNodes
  const hasSubWorkflowNodes = preview.subWorkflowNodes.length > 0

  return (
    <Stack hasGutter>
      <StackItem>
        <Content component="p">
          <strong>{stepCount}</strong> {stepCount === 1 ? 'step' : 'steps'} and <strong>{connectionCount}</strong>{' '}
          {connectionCount === 1 ? 'connection' : 'connections'} will be copied. Trigger steps from the source are not
          included.
        </Content>
        {hasSubWorkflowNodes && (
          <Content component="small">Copied sub-workflow steps still call the same child workflows.</Content>
        )}
      </StackItem>
      {resourceRefs.length > 0 && (
        <StackItem>
          <Alert
            variant="danger"
            isInline
            title="Embedding is blocked: this workflow references credentials or integrations."
          >
            <Content component="p">
              {resourceRefs.length} copied step(s) reference project-scoped resources. Permission to use them cannot be
              verified at copy time, so embedding is held pending the authorization review. Remove these references from
              the source workflow, or wait for the decision, before embedding.
            </Content>
            <List>
              {resourceRefs.map((n) => (
                <ListItem key={n.nodeId}>{n.fields.join(', ')}</ListItem>
              ))}
            </List>
          </Alert>
        </StackItem>
      )}
      {selfReferenceCount > 0 && (
        <StackItem>
          <Alert
            variant="danger"
            isInline
            title="Embedding is blocked: this workflow references the workflow you're editing."
          >
            <Content component="p">
              {selfReferenceCount} copied step(s) reference the current workflow. Embedding them would make the workflow
              call itself, creating a loop. Remove the self-reference from the source workflow before embedding.
            </Content>
          </Alert>
        </StackItem>
      )}
      {preview.danglingExpressionRefs.length > 0 && (
        <StackItem>
          <Alert variant="warning" isInline title="Some expressions reference steps that are not copied.">
            Review the copied steps after embedding; references to excluded trigger steps will need updating.
          </Alert>
        </StackItem>
      )}
    </Stack>
  )
}

export function EmbedWorkflowDialog({ isOpen, onClose, projectId, currentWorkflowId }: EmbedWorkflowDialogProps) {
  const { workflows, isLoading, isError } = useEmbeddableWorkflows(projectId, currentWorkflowId)
  const { insertEmbeddedGraph } = useEmbedWorkflow()
  const { showSuccess, showError } = useAlerts()

  const [isSelectOpen, setIsSelectOpen] = useState(false)
  const [selectedId, setSelectedId] = useState('')
  const [sourceName, setSourceName] = useState('')
  const [preview, setPreview] = useState<CopyWorkflowGraphResult | null>(null)
  const [isFetching, setIsFetching] = useState(false)
  // Guards against a stale version fetch: re-picking (or closing) bumps the id, so an
  // earlier in-flight response that resolves later is ignored instead of overwriting the
  // current preview.
  const selectRequestId = useRef(0)

  const reset = () => {
    selectRequestId.current += 1
    setSelectedId('')
    setSourceName('')
    setPreview(null)
    setIsFetching(false)
    setIsSelectOpen(false)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleSelect = (value: string) => {
    const requestId = (selectRequestId.current += 1)
    setSelectedId(value)
    setPreview(null)
    const workflow = workflows.find((w) => w.id === value)
    const version = workflow?.published_version_number
    setSourceName(workflow?.name ?? '')
    if (!workflow || typeof version !== 'number') {
      showError({ title: 'Cannot embed workflow', description: 'Selected workflow has no published version.' })
      return
    }
    setIsFetching(true)
    workflowFetchClient
      .GET('/workflows/{workflow_id}/versions/{version}', { params: { path: { workflow_id: value, version } } })
      .then(({ data, error }) => {
        if (requestId !== selectRequestId.current) return // superseded by a newer pick
        if (error || !data?.workflow_definition) {
          showError({ title: 'Cannot embed workflow', description: getErrorMessage(error) })
          return
        }
        setPreview(copyWorkflowGraph(data.workflow_definition))
      })
      .catch((err: unknown) => {
        if (requestId !== selectRequestId.current) return
        showError({ title: 'Cannot embed workflow', description: getErrorMessage(err) })
      })
      .finally(() => {
        if (requestId === selectRequestId.current) setIsFetching(false)
      })
  }

  const hasResourceRefs = (preview?.resourceReferenceNodes.length ?? 0) > 0
  // A copied sub_workflow step that points back at the workflow being edited would make it
  // call itself (a loop), so Embed is blocked when the source references the current workflow.
  const selfReferenceCount =
    preview && currentWorkflowId ? preview.subWorkflowNodes.filter((n) => n.workflowId === currentWorkflowId).length : 0
  const hasSelfReference = selfReferenceCount > 0
  const canEmbed = !!preview && !isFetching && !hasResourceRefs && !hasSelfReference
  const embedDisabledReason = getEmbedDisabledReason({
    hasPreview: !!preview,
    isFetching,
    hasResourceRefs,
    hasSelfReference,
  })

  const handleEmbed = () => {
    if (!preview || !canEmbed) return
    insertEmbeddedGraph(preview)
    showSuccess({
      title: 'Workflow embedded',
      description: `${preview.activities.length} step(s) from "${sourceName}" were copied onto the canvas.`,
    })
    handleClose()
  }

  const renderPicker = () => {
    if (isLoading) return <Spinner size="md" aria-label="Loading workflows" />
    if (isError) return <Alert variant="danger" isInline title="Could not load workflows in this project." />
    return (
      <SynSelect
        id="embed-workflow-select"
        isOpen={isSelectOpen}
        selected={selectedId || undefined}
        onSelect={(_event, value) => {
          handleSelect(String(value))
          setIsSelectOpen(false)
        }}
        onOpenChange={setIsSelectOpen}
        toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
          <MenuToggle
            ref={toggleRef}
            onClick={() => setIsSelectOpen((prev) => !prev)}
            isExpanded={isSelectOpen}
            isFullWidth
            isDisabled={isFetching}
            aria-label="Select a published workflow"
          >
            {selectedId ? sourceName : 'Select a published workflow'}
          </MenuToggle>
        )}
      >
        <SelectList>
          {workflows.map((w) => (
            <SelectOption key={w.id} value={w.id}>
              {w.name}
            </SelectOption>
          ))}
        </SelectList>
      </SynSelect>
    )
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small" aria-labelledby="embed-workflow-title">
      <ModalHeader title="Embed published workflow" labelId="embed-workflow-title" />
      <ModalBody>
        <Stack hasGutter>
          <StackItem>
            <Content component="p">
              You can only embed published workflows from the same project as the workflow you&apos;re editing.
              Embedding copies steps onto your canvas, where they stay independent of the source workflow. Triggers are
              excluded.
            </Content>
          </StackItem>
          <StackItem>
            <Form>
              <FormGroup label="Published workflow" isRequired fieldId="embed-workflow-select">
                {renderPicker()}
              </FormGroup>
            </Form>
          </StackItem>

          {isFetching && (
            <StackItem>
              <Spinner size="md" aria-label="Preparing copy" />
            </StackItem>
          )}

          {preview && !isFetching && (
            <StackItem>
              <EmbedPreviewBody preview={preview} selfReferenceCount={selfReferenceCount} />
            </StackItem>
          )}
        </Stack>
      </ModalBody>
      <ModalFooter>
        {canEmbed ? (
          <Button key="embed" variant="primary" onClick={handleEmbed}>
            Embed workflow
          </Button>
        ) : (
          <Tooltip content={embedDisabledReason ?? 'Embedding is not available.'}>
            <Button key="embed" variant="primary" onClick={handleEmbed} isAriaDisabled>
              Embed workflow
            </Button>
          </Tooltip>
        )}
        <Button key="cancel" variant="link" onClick={handleClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
