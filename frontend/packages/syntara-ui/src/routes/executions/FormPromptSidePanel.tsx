import { Stack, StackItem } from '@patternfly/react-core'
import type { FormsAPI } from '@syntara/contracts'
import { useRef } from 'react'

import { ApprovalNavigationHeader } from '../../components/ApprovalNavigationHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SidePanelHeader } from '../../components/SidePanelHeader'
import { useSidePanelFocusOnOpen } from '../../hooks/useSidePanelFocusOnOpen'

import styles from './ApprovalSidePanel.module.css'
import { FORM_PROMPT_RESPOND_PANEL_TITLE } from './formPrompt/formPromptRespondPanelConstants'
import { FormPromptResponseContent } from './FormPromptResponseContent'

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
}>

export function FormPromptSidePanel({
  executionId,
  formPrompt,
  activityNameMap,
  onClose,
  onSubmitted,
  currentIndex,
  totalCount,
  hasPrev,
  hasNext,
  onNavigatePrev,
  onNavigateNext,
}: FormPromptSidePanelProps) {
  const panelRootRef = useRef<HTMLElement>(null)
  useSidePanelFocusOnOpen(true, panelRootRef)

  const showNavigation = totalCount !== undefined && totalCount > 1 && onNavigatePrev && onNavigateNext
  const promptId = formPrompt.id
  if (!promptId) {
    return null
  }

  return (
    <SynPanel hasNoPadding isFullHeight className={styles.panel}>
      <section ref={panelRootRef} className={styles.panelInner} aria-label={FORM_PROMPT_RESPOND_PANEL_TITLE}>
        <Stack className={styles.panelStack}>
          <StackItem className={styles.headerPadding}>
            {showNavigation ? (
              <ApprovalNavigationHeader
                title={FORM_PROMPT_RESPOND_PANEL_TITLE}
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
              <SidePanelHeader
                title={FORM_PROMPT_RESPOND_PANEL_TITLE}
                onClose={onClose}
                closeAriaLabel="Close form prompt panel"
              />
            )}
          </StackItem>

          <StackItem isFilled className={styles.bodyPadding}>
            <FormPromptResponseContent
              key={`${executionId}:${promptId}`}
              executionId={executionId}
              formPromptId={promptId}
              activityNameMap={activityNameMap}
              onSubmitted={onSubmitted}
            />
          </StackItem>
        </Stack>
      </section>
    </SynPanel>
  )
}
