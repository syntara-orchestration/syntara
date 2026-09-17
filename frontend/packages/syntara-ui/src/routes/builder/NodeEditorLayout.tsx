import { Alert, Button, Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import { RhUiExternalLinkIcon } from '@patternfly/react-icons'
import type { Node } from '@xyflow/react'
import type { ReactNode } from 'react'

import { SynPanel } from '../../components/layout/SynPanel'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import { NodeFormTabBarProvider } from './node-forms/shared/NodeFormTabBarContext'
import { useNodeExecutionData } from './panels/hooks/useNodeExecutionData'
import { NodeEditorPanelBody } from './panels/NodeEditorPanelBody'
import type { WorkflowMetadata } from './types/workflowMetadata'

function DocumentationButton({ href }: Readonly<{ href: string }>) {
  return (
    <Button
      variant="link"
      icon={<RhUiExternalLinkIcon />}
      iconPosition="end"
      component="a"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Documentation (opens in a new tab)"
    >
      Documentation
    </Button>
  )
}

type NodeEditorLayoutProps = {
  parametersContent: ReactNode
  headerContent?: ReactNode
  headerIcon?: ReactNode
  headerActions?: ReactNode
  docLink?: string
  showInputPanel: boolean
  nodeId?: string
  node?: Node<NodeType['data']>
  executionId?: string | null
  workflowId?: string | null
  onClose?: () => void
  showClose?: boolean
  sourceNodeId?: string | null
  formId?: string
  showNavigation?: boolean
  onNavigateToNode?: (nodeId: string) => void
  onAddStep?: (handle?: string) => void
  workflowMetadata?: WorkflowMetadata
  tabBarAction?: ReactNode
  readOnly?: boolean
  mode?: 'add' | 'edit'
}

export function NodeEditorLayout({
  parametersContent,
  headerContent,
  headerIcon,
  headerActions,
  docLink,
  showInputPanel,
  nodeId,
  node,
  executionId,
  workflowId,
  onClose,
  showClose = true,
  sourceNodeId,
  formId,
  showNavigation = false,
  onNavigateToNode,
  onAddStep,
  workflowMetadata,
  tabBarAction,
  readOnly,
  mode = 'edit',
}: NodeEditorLayoutProps) {
  const { inputData, outputData } = useNodeExecutionData(nodeId ?? '', executionId, workflowId)
  let closeAriaLabel = 'Cancel without saving'
  if (readOnly) closeAriaLabel = 'Close node editor'
  else if (mode === 'add') closeAriaLabel = 'Cancel step creation'

  return (
    <SynPanel
      hasNoPadding
      isFullHeight
      isGlass={false}
      opaqueFloatingFill
      style={{
        height: '100%',
        maxHeight: '100%',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Stack style={{ flex: 1, minHeight: 0, height: '100%', overflow: 'hidden' }}>
        <StackItem style={{ padding: 'var(--pf-t--global--spacer--sm)' }}>
          <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
            <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0 }}>
              <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
                {headerIcon && (
                  <FlexItem
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      paddingLeft: 'var(--pf-t--global--spacer--xs)',
                      paddingRight: 'var(--pf-t--global--spacer--xs)',
                    }}
                  >
                    {headerIcon}
                  </FlexItem>
                )}
                {headerContent && <FlexItem>{headerContent}</FlexItem>}
              </Flex>
            </FlexItem>
            <FlexItem>
              <Flex
                justifyContent={{ default: 'justifyContentFlexEnd' }}
                alignItems={{ default: 'alignItemsCenter' }}
                gap={{ default: 'gapSm' }}
              >
                {docLink ? (
                  <FlexItem>
                    <DocumentationButton href={docLink} />
                  </FlexItem>
                ) : null}
                {headerActions && !readOnly && <FlexItem>{headerActions}</FlexItem>}
                {showClose && (
                  <>
                    <FlexItem>
                      <Button
                        variant={readOnly ? 'secondary' : 'link'}
                        size={readOnly ? 'sm' : undefined}
                        onClick={() => {
                          onClose?.()
                        }}
                        aria-label={closeAriaLabel}
                        type="button"
                      >
                        {readOnly ? 'Close' : 'Cancel'}
                      </Button>
                    </FlexItem>
                    {!readOnly && (
                      <FlexItem>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            if (formId) {
                              const element = document.getElementById(formId)
                              if (element instanceof HTMLFormElement) {
                                element.requestSubmit()
                              } else {
                                onClose?.()
                              }
                            } else {
                              onClose?.()
                            }
                          }}
                          type="button"
                        >
                          {mode === 'add' ? 'Create' : 'Update'}
                        </Button>
                      </FlexItem>
                    )}
                  </>
                )}
              </Flex>
            </FlexItem>
          </Flex>
        </StackItem>
        {readOnly && (
          <StackItem style={{ padding: '0 var(--pf-t--global--spacer--sm)' }}>
            <Alert
              variant="info"
              isInline
              title="You are viewing a previous version. Return to the editor to make changes."
            />
          </StackItem>
        )}
        <StackItem
          isFilled
          style={{
            minHeight: 0,
            overflow: 'visible',
            padding: 'var(--pf-t--global--spacer--sm) 0',
          }}
        >
          <NodeEditorPanelBody
            showInputPanel={showInputPanel}
            showNavigation={showNavigation}
            nodeId={nodeId}
            node={node}
            sourceNodeId={sourceNodeId}
            inputData={inputData}
            outputData={outputData}
            parametersContent={
              <NodeFormTabBarProvider tabBarAction={tabBarAction}>{parametersContent}</NodeFormTabBarProvider>
            }
            onNavigateToNode={onNavigateToNode}
            onAddStep={onAddStep}
            workflowMetadata={workflowMetadata}
          />
        </StackItem>
      </Stack>
    </SynPanel>
  )
}
