import { Stack, StackItem } from '@patternfly/react-core'
import type { FormsAPI } from '@syntara/contracts'
import { memo, useRef, type RefObject } from 'react'

import { ApprovalNavigationHeader } from '../../components/ApprovalNavigationHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SidePanelHeader } from '../../components/SidePanelHeader'
import { useSidePanelFocusOnOpen } from '../../hooks/useSidePanelFocusOnOpen'

import approvalStyles from './ApprovalSidePanel.module.css'
import {
  FormPromptRespondPanelFooterProvider,
  useFormPromptRespondPanelFooterSnapshot,
} from './formPrompt/FormPromptRespondPanelFooter'
import type { WorkflowDefinitionLike } from './formPrompt/resolveCanvasNodeType'
import { FormPromptResponseContent } from './FormPromptResponseContent'
import styles from './FormPromptSidePanel.module.css'

type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']

type FormPromptSidePanelProps = Readonly<{
  executionId: string
  formPrompt: FormPromptSummary
  activityNameMap?: Map<string, string>
  onClose: () => void
  onSubmitted: () => void
  currentIndex?: number
  totalCount?: number
  hasPrev?: boolean
  hasNext?: boolean
  onNavigatePrev?: () => void
  onNavigateNext?: () => void
  workflowDefinition?: WorkflowDefinitionLike
}>

export function FormPromptSidePanel(props: FormPromptSidePanelProps) {
  const panelRootRef = useRef<HTMLDivElement>(null)
  useSidePanelFocusOnOpen(true, panelRootRef)

  const promptId = props.formPrompt.id
  if (!promptId) {
    return null
  }

  return (
    <FormPromptRespondPanelFooterProvider>
      <FormPromptSidePanelFrame {...props} panelRootRef={panelRootRef} promptId={promptId} />
    </FormPromptRespondPanelFooterProvider>
  )
}

type FormPromptSidePanelFrameProps = FormPromptSidePanelProps &
  Readonly<{
    panelRootRef: RefObject<HTMLDivElement | null>
    promptId: string
  }>

function FormPromptSidePanelFrame(props: FormPromptSidePanelFrameProps) {
  const panelFooter = useFormPromptRespondPanelFooterSnapshot()

  return (
    <SynPanel
      hasNoPadding
      isFullHeight
      footer={panelFooter}
      className={approvalStyles.panel}
      panelMainBodyProps={{
        style: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' },
      }}
    >
      <FormPromptSidePanelBody {...props} />
    </SynPanel>
  )
}

const FormPromptSidePanelBody = memo(function FormPromptSidePanelBody({
  executionId,
  activityNameMap,
  onClose,
  onSubmitted,
  currentIndex,
  totalCount,
  hasPrev,
  hasNext,
  onNavigatePrev,
  onNavigateNext,
  workflowDefinition,
  panelRootRef,
  promptId,
}: FormPromptSidePanelFrameProps) {
  const showNavigation = totalCount !== undefined && totalCount > 1 && onNavigatePrev && onNavigateNext

  return (
    <div ref={panelRootRef} className={approvalStyles.panelInner}>
      <Stack className={approvalStyles.panelStack}>
        <StackItem className={approvalStyles.headerPadding}>
          {showNavigation ? (
            <ApprovalNavigationHeader
              title="Respond to prompt"
              currentIndex={currentIndex}
              totalCount={totalCount}
              hasPrev={hasPrev}
              hasNext={hasNext}
              onNavigatePrev={onNavigatePrev}
              onNavigateNext={onNavigateNext}
              onClose={onClose}
              closeAriaLabel="Close form prompt panel"
              navigatePrevAriaLabel="Previous prompt"
              navigateNextAriaLabel="Next prompt"
            />
          ) : (
            <SidePanelHeader title="Respond to prompt" onClose={onClose} closeAriaLabel="Close form prompt panel" />
          )}
        </StackItem>

        <StackItem isFilled className={`${approvalStyles.bodyPadding} ${styles.bodyPadding}`}>
          <div className={styles.bodyHost}>
            <FormPromptResponseContent
              key={`${executionId}:${promptId}`}
              executionId={executionId}
              formPromptId={promptId}
              activityNameMap={activityNameMap}
              onSubmitted={onSubmitted}
              workflowDefinition={workflowDefinition}
            />
          </div>
        </StackItem>
      </Stack>
    </div>
  )
})
