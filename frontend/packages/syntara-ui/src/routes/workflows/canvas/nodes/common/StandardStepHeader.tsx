import { Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import { useStore } from '@xyflow/react'

import { SynStepHeader } from '../../../../../components/steps/SynStepHeader'
import { SynStepHeaderActions } from '../../../../../components/steps/SynStepHeaderActions'
import { SynStepTitle } from '../../../../../components/steps/SynStepTitle'
import { useIsActiveExecution } from '../../../../builder/ActiveExecutionContext'
import { useIsExecutionView } from '../../../../builder/ExecutionViewContext'
import { useIsVersionView } from '../../../../builder/VersionViewContext'
import type { StepMenuAction } from '../hooks/useStepMenuActions'

import headerStyles from './StandardStepHeader.module.css'

type StandardStepHeaderProps = {
  icon?: React.ReactNode
  /** Optional badge rendered just under the icon, above title/subtitle */
  badge?: React.ReactNode
  title?: string
  subtitle?: string
  expandable?: boolean
  menuActions?: StepMenuAction[]
  /** When set, used for header action row menu popper (e.g. semantic zoom preview). */
  menuPopperProps?: React.ComponentProps<typeof SynStepHeaderActions>['menuPopperProps']
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
        <SynStepHeader className={headerStyles.headerSection}>
          <Flex
            alignItems={{ default: 'alignItemsCenter' }}
            justifyContent={{ default: 'justifyContentSpaceBetween' }}
            className={headerStyles.actionRow}
          >
            {props.icon ? (
              <FlexItem shrink={{ default: 'shrink' }}>{props.icon}</FlexItem>
            ) : (
              <FlexItem grow={{ default: 'grow' }} />
            )}
            <FlexItem shrink={{ default: 'shrink' }}>
              <SynStepHeaderActions
                stepTitle={stepTitle}
                menuActions={props.menuActions}
                expandable={props.expandable}
                showMenuActions={showMenuActions}
                menuPopperProps={props.menuPopperProps}
              />
            </FlexItem>
          </Flex>
          {(props.title || props.subtitle) && (
            <div className={headerStyles.titleRow}>
              <SynStepTitle title={props.title ?? ''} subTitle={props.subtitle ?? ''} />
            </div>
          )}
        </SynStepHeader>
      </StackItem>
      {props.badge ? <StackItem style={badgeSectionStyle}>{props.badge}</StackItem> : null}
    </Stack>
  )
}
