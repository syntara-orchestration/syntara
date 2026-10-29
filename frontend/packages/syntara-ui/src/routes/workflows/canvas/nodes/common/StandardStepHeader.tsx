import { Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import { useStore } from '@xyflow/react'

import { SynStepHeader } from '../../../../../components/steps/SynStepHeader'
import { SynStepHeaderActions } from '../../../../../components/steps/SynStepHeaderActions'
import { SynStepTitle } from '../../../../../components/steps/SynStepTitle'
import { useIsActiveExecution } from '../../../../builder/ActiveExecutionContext'
import { useIsExecutionView } from '../../../../builder/ExecutionViewContext'
import { useIsVersionView } from '../../../../builder/VersionViewContext'
import type { StepMenuAction } from '../hooks/useStepMenuActions'

type StandardStepHeaderProps = {
  icon?: React.ReactNode
  /** Optional badge rendered just under the icon, above title/subtitle */
  badge?: React.ReactNode
  title?: string
  subtitle?: string
  expandable?: boolean
  menuActions?: StepMenuAction[]
}

const sectionPadding = {
  paddingLeft: 'var(--pf-t--global--spacer--md)',
  paddingRight: 'var(--pf-t--global--spacer--md)',
}

const badgeSectionStyle = {
  ...sectionPadding,
  paddingTop: 'var(--pf-t--global--spacer--xs)',
  paddingBottom: 0,
}

/**
 * Standard step header component that combines icon, title, subtitle, optional expand toggle, and kebab menu.
 * Reduces boilerplate in step component implementations.
 *
 * The kebab menu supports:
 * - Custom actions via additionalActions prop in useStepMenuActions
 * - Automatic separator before delete action when custom actions exist
 * - Danger styling for destructive actions (variant: 'danger')
 * - Icons for menu items
 *
 * The kebab menu is automatically hidden in execution view mode (read-only).
 */
export function StandardStepHeader(props: Readonly<StandardStepHeaderProps>) {
  const isExecutionView = useIsExecutionView()
  const isActiveExecution = useIsActiveExecution()
  const nodesConnectable = useStore((s) => s.nodesConnectable)
  const isVersionView = useIsVersionView()

  const stepTitle = props.title ?? props.subtitle ?? ''
  const showMenuActions =
    Boolean(props.menuActions?.length) && !isExecutionView && !isActiveExecution && !isVersionView && nodesConnectable

  return (
    <Stack>
      <StackItem>
        <SynStepHeader>
          <Flex
            alignItems={{ default: 'alignItemsFlexStart' }}
            justifyContent={{ default: 'justifyContentSpaceBetween' }}
            style={{ gap: 'var(--pf-t--global--spacer--sm)' }}
          >
            <Flex
              alignItems={{ default: 'alignItemsFlexStart' }}
              style={{ gap: 'var(--pf-t--global--spacer--sm)', minWidth: 0, flex: 1 }}
            >
              {props.icon ? <FlexItem shrink={{ default: 'shrink' }}>{props.icon}</FlexItem> : null}
              {(props.title || props.subtitle) && (
                <SynStepTitle title={props.title ?? ''} subTitle={props.subtitle ?? ''} />
              )}
            </Flex>
            <FlexItem shrink={{ default: 'shrink' }}>
              <SynStepHeaderActions
                stepTitle={stepTitle}
                menuActions={props.menuActions}
                expandable={props.expandable}
                showMenuActions={showMenuActions}
              />
            </FlexItem>
          </Flex>
        </SynStepHeader>
      </StackItem>
      {props.badge ? <StackItem style={badgeSectionStyle}>{props.badge}</StackItem> : null}
    </Stack>
  )
}
