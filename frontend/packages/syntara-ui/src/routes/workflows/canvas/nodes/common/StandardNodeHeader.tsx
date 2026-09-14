import { Content, Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import { useStore } from '@xyflow/react'

import { useIsActiveExecution } from '../../../../builder/ActiveExecutionContext'
import { useIsExecutionView } from '../../../../builder/ExecutionViewContext'
import { useIsVersionView } from '../../../../builder/VersionViewContext'
import type { NodeMenuAction } from '../hooks/useNodeMenuActions'

import { NodeExpandToggle } from './NodeExpandToggle'
import { NodeHeader } from './NodeHeader'
import { NodeMenu } from './NodeMenu'
import { NodeTitle } from './NodeTitle'

type StandardNodeHeaderProps = {
  icon?: React.ReactNode
  /** Optional badge rendered just under the icon, above title/subtitle */
  badge?: React.ReactNode
  title?: string
  subtitle?: string
  expandable?: boolean
  menuActions?: NodeMenuAction[]
}

/**
 * Standard node header component that combines icon, title, subtitle, optional expand toggle, and kebab menu.
 * Reduces boilerplate in node component implementations.
 *
 * The kebab menu supports:
 * - Custom actions via additionalActions prop in useNodeMenuActions
 * - Automatic separator before delete action when custom actions exist
 * - Danger styling for destructive actions (variant: 'danger')
 * - Icons for menu items
 *
 * The kebab menu is automatically hidden in execution view mode (read-only).
 *
 * Layout: Icon and kebab menu on first line, title and subtitle on second line below.
 */
const sectionPadding = {
  paddingLeft: 'var(--pf-t--global--spacer--md)',
  paddingRight: 'var(--pf-t--global--spacer--md)',
}

const badgeSectionStyle = {
  ...sectionPadding,
  paddingTop: 'var(--pf-t--global--spacer--xs)',
  paddingBottom: 0,
}

const titleSectionStyle = {
  ...sectionPadding,
  paddingTop: 'var(--pf-t--global--spacer--xs)',
  paddingBottom: 'var(--pf-t--global--spacer--sm)',
}

export function StandardNodeHeader(props: Readonly<StandardNodeHeaderProps>) {
  const isExecutionView = useIsExecutionView()
  const isActiveExecution = useIsActiveExecution()
  const nodesConnectable = useStore((s) => s.nodesConnectable)
  const isVersionView = useIsVersionView()

  return (
    <Stack>
      <StackItem>
        <NodeHeader>
          {props.icon && <FlexItem>{props.icon}</FlexItem>}
          <FlexItem>
            <Flex>
              {props.expandable && (
                <FlexItem>
                  <NodeExpandToggle />
                </FlexItem>
              )}
              {props.menuActions &&
                props.menuActions.length > 0 &&
                !isExecutionView &&
                !isActiveExecution &&
                !isVersionView &&
                nodesConnectable && (
                  <FlexItem>
                    <NodeMenu menuActions={props.menuActions} />
                  </FlexItem>
                )}
            </Flex>
          </FlexItem>
        </NodeHeader>
      </StackItem>
      {props.badge && <StackItem style={badgeSectionStyle}>{props.badge}</StackItem>}
      {(props.title || props.subtitle) && (
        <StackItem style={titleSectionStyle}>
          <Content>
            <NodeTitle title={props.title ?? ''} subTitle={props.subtitle ?? ''} />
          </Content>
        </StackItem>
      )}
    </Stack>
  )
}
