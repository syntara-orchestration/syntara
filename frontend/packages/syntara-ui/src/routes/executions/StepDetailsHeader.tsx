import { Content, ContentVariants, Flex, FlexItem, StackItem, Title, TitleSizes } from '@patternfly/react-core'

import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { ActivityStatusLabel } from '../builder/ExecutionStatus'
import type { ActivityState } from '../workflows/execution/types'

import styles from './StepExecutionDetailsPanel.module.css'

type StepDetailsHeaderProps = {
  stepName: string
  stepStarted: string | null
  stepCompleted: string | null
  stepElapsedLabel?: string
  status?: ActivityState['status']
  nodeType?: string
  replayed: boolean
  retainedFailure: boolean
  triggerInputReused: boolean
}

export function StepDetailsHeader({
  stepName,
  stepStarted,
  stepCompleted,
  stepElapsedLabel,
  status,
  nodeType,
  replayed,
  retainedFailure,
  triggerInputReused,
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
        {(stepStarted || stepCompleted || stepElapsedLabel || status) && (
          <FlexItem>
            <Flex
              gap={{ default: 'gapMd' }}
              alignItems={{ default: 'alignItemsCenter' }}
              role="group"
              aria-label="Step timing and status"
            >
              {(stepStarted || stepCompleted) && (
                <Content
                  component={ContentVariants.small}
                  style={{ color: 'var(--pf-t--global--text--color--subtle)', margin: 0 }}
                >
                  {stepStarted && <ExecutionTimestamp dateString={stepStarted} />}
                  {stepStarted && stepCompleted && ' - '}
                  {stepCompleted && <ExecutionTimestamp dateString={stepCompleted} />}
                </Content>
              )}
              {stepElapsedLabel && (
                <Content
                  component={ContentVariants.small}
                  style={{ color: 'var(--pf-t--global--text--color--subtle)', margin: 0 }}
                >
                  Elapsed time: {stepElapsedLabel}
                </Content>
              )}
              {status && (
                <FlexItem style={{ display: 'flex', alignItems: 'center' }}>
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
