import {
  Alert,
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  List,
  ListItem,
  Spinner,
  Stack,
  StackItem,
  Title,
  TitleSizes,
} from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../app/AppRoute'
import { SynPanel } from '../../components/layout/SynPanel'
import { SidePanelHeader } from '../../components/SidePanelHeader'
import { detachPromise } from '../../utils/detachPromise'

import { useRetryFromFailure } from './hooks/useRetryFromFailure'
import { useRetryFromFailurePreview } from './hooks/useRetryFromFailurePreview'
import { canConfirmRetryFromFailure, getRetryPlanPoints, selectedRetryPointId } from './retryFromFailure'
import styles from './RetryFromFailureSidePanel.module.css'

type RetryFromFailureSidePanelProps = Readonly<{
  executionId: string
  activityNameMap: ReadonlyMap<string, string>
  selectedNodeId?: string | null
  onClose: () => void
}>

function retryPathStepLabel(stepCount: number | undefined): string {
  if (stepCount === undefined) return 'Included in the retry plan'

  const stepLabel = stepCount === 1 ? 'step' : 'steps'
  return `${stepCount} ${stepLabel} in this retry path`
}

/** Full in-context retry review shown beside the source execution. */
export function RetryFromFailureSidePanel({
  executionId,
  activityNameMap,
  selectedNodeId,
  onClose,
}: RetryFromFailureSidePanelProps) {
  const navigate = useNavigate()
  const { preview, isLoading, isError } = useRetryFromFailurePreview({ executionId, enabled: true })
  const retry = useRetryFromFailure({
    executionId,
    onSuccess: (newExecutionId) => {
      onClose()
      detachPromise(
        navigate({ to: AppRoute.Executions.Execution.replace(':executionId', newExecutionId) })
      )
    },
  })

  const points = getRetryPlanPoints(preview, activityNameMap)
  const selectedRetryPoint = selectedRetryPointId(selectedNodeId, preview)
  const visiblePoints = selectedRetryPoint ? points.filter((point) => point.id === selectedRetryPoint) : points
  const isRetryDisabled = !canConfirmRetryFromFailure(preview, isLoading, isError) || retry.isPending
  const totalSteps = selectedRetryPoint
    ? preview?.step_count_by_eligible_point?.[selectedRetryPoint]
    : preview?.total_step_count

  let planContent: React.ReactNode
  if (isLoading) {
    planContent = (
      <Content component={ContentVariants.p}>
        <Spinner size="md" aria-label="Loading retry plan" /> Checking which steps will run again…
      </Content>
    )
  } else if (isError) {
    planContent = (
      <Alert isInline variant="danger" title="Could not load retry plan" data-testid="retry-preview-error">
        The retry plan could not be loaded. Close this panel and try again.
      </Alert>
    )
  } else if (preview && !preview.eligible) {
    planContent = (
      <Alert isInline variant="warning" title="This run cannot be retried from failure" data-testid="retry-rejected">
        {preview.reason ?? 'No failed steps were found to retry from.'}
      </Alert>
    )
  } else if (points.length === 0) {
    planContent = (
      <Alert isInline variant="warning" title="No retry points found" data-testid="retry-no-points">
        No failed steps were found to retry from.
      </Alert>
    )
  } else {
    planContent = (
      <Stack hasGutter>
        <StackItem>
          <Flex className={styles.summary} gap={{ default: 'gapLg' }}>
            <FlexItem>
              <strong className={styles.summaryNumber}>{totalSteps ?? '—'}</strong>
              <Content component={ContentVariants.small}>steps to retry</Content>
            </FlexItem>
            <FlexItem>
              <strong className={styles.summaryNumber}>{visiblePoints.length}</strong>
              <Content component={ContentVariants.small}>starting points</Content>
            </FlexItem>
          </Flex>
        </StackItem>
        <StackItem>
          <Title headingLevel="h4" size={TitleSizes.md}>
            Starting points
          </Title>
          <List isPlain aria-label="Failure points included in the retry">
            {visiblePoints.map((point) => {
              return (
                <ListItem key={point.id}>
                  <div className={styles.retryPoint}>
                    <strong>{point.name}</strong>
                    <Content component={ContentVariants.small}>{retryPathStepLabel(point.stepCount)}</Content>
                  </div>
                </ListItem>
              )
            })}
          </List>
        </StackItem>
        <StackItem>
          <Content component={ContentVariants.small} data-testid="retry-retained-results-copy">
            Completed results outside these retry paths keep their original output. The total above counts shared
            downstream steps only once.
          </Content>
        </StackItem>
        <StackItem>
          <Content component={ContentVariants.small}>
            Select a failed step in Run details to retry from only that point. With no eligible failure selected, the
            default retry scope is used.
          </Content>
        </StackItem>
      </Stack>
    )
  }

  const footer = (
    <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
      <FlexItem>
        <Button variant="link" onClick={onClose} isDisabled={retry.isPending}>
          Cancel
        </Button>
      </FlexItem>
      <FlexItem>
        <Button
          variant="primary"
          onClick={() => retry.handleRetry(selectedRetryPoint ? [selectedRetryPoint] : undefined)}
          isLoading={retry.isPending}
          isDisabled={isRetryDisabled}
          data-testid="retry-from-failure-confirm"
        >
          Retry from failure
        </Button>
      </FlexItem>
    </Flex>
  )

  return (
    <aside className={styles.panel} aria-label="Retry from failure review" data-testid="retry-from-failure-panel">
      <SynPanel hasNoPadding isFullHeight isScrollable footer={footer}>
        <div className={styles.panelInner}>
          <Stack className={styles.panelStack}>
            <StackItem className={styles.headerPadding}>
              <SidePanelHeader title="Retry from failure" onClose={onClose} closeAriaLabel="Close retry review" />
            </StackItem>
            <StackItem isFilled className={styles.bodyPadding}>
              <Stack hasGutter>
                <StackItem>
                  <Title headingLevel="h3" size={TitleSizes.md}>
                    How retry works
                  </Title>
                  <List>
                    <ListItem>The retry uses the same workflow version as this run.</ListItem>
                    <ListItem>
                      Failed steps and affected downstream steps run again. Completed results outside those paths are
                      reused.
                    </ListItem>
                    <ListItem>External side effects from the original run are not undone.</ListItem>
                  </List>
                </StackItem>
                <StackItem>
                  <Title headingLevel="h3" size={TitleSizes.md}>
                    Retry plan
                  </Title>
                  {planContent}
                </StackItem>
              </Stack>
            </StackItem>
          </Stack>
        </div>
      </SynPanel>
    </aside>
  )
}
