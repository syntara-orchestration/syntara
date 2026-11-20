import { Content, ContentVariants, Flex, FlexItem, StackItem, Title, TitleSizes } from '@patternfly/react-core'

import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { ActivityStatusLabel } from '../builder/ExecutionStatus'
import type { ActivityState } from '../workflows/execution/types'

import styles from './StepExecutionDetailsPanel.module.css'

type StepDetailsHeaderProps = {
  stepName: string
  startedAt: string | null
  completedAt: string | null
  elapsedLabel: string | null
  status?: ActivityState['status']
  nodeType?: string
  replayed?: boolean
  retainedFailure?: boolean
  triggerInputReused?: boolean
}

export function StepDetailsHeader({
  stepName,
  startedAt,
  completedAt,
  elapsedLabel,
  status,
  nodeType,
  replayed = false,
  retainedFailure = false,
  triggerInputReused = false,
}: Readonly<StepDetailsHeaderProps>) {
  return (
    <StackItem className={styles.headerRow}>
      <Flex
        justifyContent={{ default: 'justifyContentSpaceBetween' }}
        alignItems={{ default: 'alignItemsCenter' }}
        role="group"
        aria-label="Step details header"
      >
        <FlexItem>
          <Title headingLevel="h2" size={TitleSizes.md} style={{ margin: 0 }}>
            {stepName}
          </Title>
        </FlexItem>
        {(startedAt || completedAt || elapsedLabel || status) && (
          <FlexItem>
            <Flex
              gap={{ default: 'gapMd' }}
              alignItems={{ default: 'alignItemsCenter' }}
              role="group"
              aria-label="Step timing and status"
            >
              {(startedAt || completedAt) && (
                <Content
                  component={ContentVariants.small}
                  style={{ color: 'var(--pf-t--global--text--color--subtle)', margin: 0 }}
                >
                  {startedAt && <ExecutionTimestamp dateString={startedAt} />}
                  {startedAt && completedAt && ' - '}
                  {completedAt && <ExecutionTimestamp dateString={completedAt} />}
                </Content>
              )}
              {elapsedLabel && (
                <Content
                  component={ContentVariants.small}
                  style={{ color: 'var(--pf-t--global--text--color--subtle)', margin: 0 }}
                >
                  Elapsed time: {elapsedLabel}
                </Content>
              )}
              {status && (
                <FlexItem>
                  <ActivityStatusLabel
                    status={status}
                    nodeType={nodeType}
                    replayed={replayed}
                    retainedFailure={retainedFailure}
                    triggerInputReused={triggerInputReused}
                  />
                </FlexItem>
              )}
            </Flex>
          </FlexItem>
        )}
      </Flex>
    </StackItem>
  )
}
