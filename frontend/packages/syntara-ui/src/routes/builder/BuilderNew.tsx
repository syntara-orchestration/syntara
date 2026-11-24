import {
  Button,
  Content,
  ContentVariants,
  FormGroup,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { ReactFlowProvider } from '@xyflow/react'
import { useCallback, useState } from 'react'

import '@xyflow/react/dist/style.css'
import { AppRoute } from '../../app/AppRoute'
import { workflowClient } from '../../client'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { detachPromise } from '../../utils/detachPromise'

import { BuilderContent } from './BuilderContent'
import styles from './BuilderNew.module.css'
import { useOnlyWorkflowProjectId } from './hooks/useOnlyWorkflowProjectId'
import { WORKFLOWS_LIST_PARAMS_FOR_DEFAULT_NAME } from './utils/workflowListQuery'

function readProjectId(search: unknown): string | undefined {
  if (typeof search !== 'object' || search === null || !('projectId' in search)) return undefined
  return typeof search.projectId === 'string' && search.projectId ? search.projectId : undefined
}

/**
 * New workflow page.
 *
 * A workflow belongs to one project, and that project decides which step types the
 * author may use (R18 / AC-4.c). So the project is chosen in a modal before the
 * builder opens, and stays fixed in the builder.
 *
 * The picker is pre-filled from `?projectId=` (the Workflows list and a project's
 * Workflows tab pass the project in view) or, when the caller can see exactly one
 * project that can hold workflows, with that project. It never inherits the project
 * last selected on another page. The author always confirms with Continue.
 */
export default function BuilderNew() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const projectIdParam = useSearch({ strict: false, select: readProjectId })
  const [confirmedProjectId, setConfirmedProjectId] = useState<string | null>(null)

  const onlyProjectId = useOnlyWorkflowProjectId()
  const { selectedProject, selectedProjectId, ProjectSelector } = useProjectSelector({
    requireProject: true,
    // The URL wins; otherwise the hook seeds the only project once the list loads.
    initialProjectId: projectIdParam ?? onlyProjectId,
    clearSelectionOnMount: true,
    showTogglePrefix: false,
    isMenuInline: true,
  })

  const isBuiltinSelected = selectedProject?.is_builtin === true
  const canContinue = !!selectedProjectId && !isBuiltinSelected
  const isBuilderOpen = !!confirmedProjectId && confirmedProjectId === projectIdParam

  const handleContinue = useCallback(() => {
    if (!canContinue || !selectedProjectId) return
    setConfirmedProjectId(selectedProjectId)
    // Warm the list the builder reads to pick a free default workflow name.
    detachPromise(
      queryClient.prefetchQuery(
        workflowClient.queryOptions('get', '/workflows', WORKFLOWS_LIST_PARAMS_FOR_DEFAULT_NAME)
      )
    )
    detachPromise(navigate({ to: AppRoute.WorkflowBuilder.New, search: { projectId: selectedProjectId } }))
  }, [canContinue, navigate, queryClient, selectedProjectId])

  const handleCancel = useCallback(() => {
    detachPromise(navigate({ to: AppRoute.Workflows.Root }))
  }, [navigate])

  const pageTitle = <SynPageTitle segments={['New Workflow', 'Workflows']} />

  if (isBuilderOpen) {
    return (
      <ReactFlowProvider>
        {pageTitle}
        <BuilderContent key={confirmedProjectId} isNew={true} workflowId={null} initialProjectId={confirmedProjectId} />
      </ReactFlowProvider>
    )
  }

  return (
    <>
      {pageTitle}
      <Modal
        isOpen
        onClose={handleCancel}
        variant="medium"
        aria-labelledby="new-workflow-project-title"
        aria-describedby="new-workflow-project-description"
      >
        <ModalHeader title="Select a project" labelId="new-workflow-project-title" />
        <ModalBody>
          <Content component={ContentVariants.p} id="new-workflow-project-description">
            Choose the project that will own this workflow. Its permissions decide who can access the workflow and which
            step types you can add, and its resources are available while you build and run it. You cannot change the
            project later.
          </Content>
          <FormGroup className={styles.projectField} label="Project" fieldId="new-workflow-project" isRequired>
            {ProjectSelector}
          </FormGroup>
          {isBuiltinSelected && (
            <Content component={ContentVariants.small}>
              Built-in projects cannot contain new workflows. Select another project to continue.
            </Content>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="primary" isDisabled={!canContinue} onClick={handleContinue}>
            Continue
          </Button>
          <Button variant="link" onClick={handleCancel}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
    </>
  )
}
