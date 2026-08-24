import { Button, Flex, FlexItem, Icon, Tooltip } from '@patternfly/react-core'
import { RhUiUndoIcon, RhUiRedoIcon } from '@patternfly/react-icons'
import { Panel } from '@xyflow/react'

import { SynPanel } from '../../../components/layout/SynPanel'
import { useWorkflowHistory } from '../../../stores/workflowStoreSelectors'

const isMac = navigator.userAgent.includes('Mac')
const UNDO_SHORTCUT_LABEL = isMac ? '⌘Z' : 'Ctrl+Z'
const REDO_SHORTCUT_LABEL = isMac ? '⌘⇧Z' : 'Ctrl+Y'

export function UndoRedoControls() {
  const { undo, redo, canUndo, canRedo } = useWorkflowHistory()

  return (
    <Panel position="bottom-center">
      <SynPanel isPill variant="raised" hasNoPadding style={{ padding: 'var(--pf-t--global--spacer--xs)' }}>
        <Flex role="toolbar" aria-label="Undo and redo" gap={{ default: 'gapNone' }}>
          <FlexItem>
            <Tooltip content={`Undo (${UNDO_SHORTCUT_LABEL})`}>
              <Button
                variant="plain"
                isCircle
                onClick={() => undo()}
                isDisabled={!canUndo}
                aria-label="Undo"
                icon={
                  <Icon isInline>
                    <RhUiUndoIcon />
                  </Icon>
                }
              />
            </Tooltip>
          </FlexItem>
          <FlexItem>
            <Tooltip content={`Redo (${REDO_SHORTCUT_LABEL})`}>
              <Button
                variant="plain"
                isCircle
                onClick={() => redo()}
                isDisabled={!canRedo}
                aria-label="Redo"
                icon={
                  <Icon isInline>
                    <RhUiRedoIcon />
                  </Icon>
                }
              />
            </Tooltip>
          </FlexItem>
        </Flex>
      </SynPanel>
    </Panel>
  )
}
