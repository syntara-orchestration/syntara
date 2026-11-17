import { Content, ContentVariants, Flex, FlexItem, StackItem, Title, TitleSizes } from '@patternfly/react-core'

import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { ActivityStatusLabel } from '../builder/ExecutionStatus'
import { getRetryActivityMarkers } from '../builder/utils/replayedNodes'
import type { ActivityState } from '../workflows/execution/types'

import styles from './StepExecutionDetailsPanel.module.css'

type StepDetailsHeaderProps = {
  stepName: string
  startedAt: string | null
  completedAt: string | null
  elapsedLabel: string | null
  status?: ActivityState['status']
  nodeType?: string
  replayBaselineAt?: string | null
}

export function StepDetailsHeader({
  stepName,
  startedAt,
  completedAt,
  elapsedLabel,
  status,
  nodeType,
  replayBaselineAt,
}: Readonly<StepDetailsHeaderProps>) {
  const replayMarkers = getRetryActivityMarkers(status ? { startedAt, status } : undefined, replayBaselineAt, nodeType)

  return (
    <StackItem className={styles.headerRow}>
      <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
        <FlexItem>
          <Title headingLevel="h2" size={TitleSizes.md} style={{ margin: 0 }}>
            {stepName}
          </Title>
        </FlexItem>
        {status && (
          <FlexItem style={{ display: 'flex', alignItems: 'center' }}>
            <ActivityStatusLabel
              status={status}
              nodeType={nodeType}
              replayed={replayMarkers.replayed}
              retainedFailure={replayMarkers.retainedFailure}
              triggerInputReused={replayMarkers.triggerInputReused}
            />
          </FlexItem>
        )}
      </Flex>
      {(startedAt || completedAt || elapsedLabel) && (
        <Flex
          className={styles.stepTiming}
          gap={{ default: 'gapMd' }}
          alignItems={{ default: 'alignItemsBaseline' }}
          flexWrap={{ default: 'nowrap' }}
        >
          {startedAt && (
            <Content component={ContentVariants.small} className={styles.stepTimingItem}>
              Started: <ExecutionTimestamp dateString={startedAt} />
            </Content>
          )}
          {completedAt && (
            <Content component={ContentVariants.small} className={styles.stepTimingItem}>
              Completed: <ExecutionTimestamp dateString={completedAt} />
            </Content>
          )}
          {elapsedLabel && (
            <Content component={ContentVariants.small} className={styles.stepTimingItem}>
              Elapsed time: {elapsedLabel}
            </Content>
          )}
        </Flex>
      )}
    </StackItem>
  )
}
