import {
  Alert,
  Button,
  Checkbox,
  Content,
  ContentVariants,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  List,
  ListItem,
  Radio,
  Spinner,
  Stack,
  StackItem,
  Title,
  TitleSizes,
} from '@patternfly/react-core'

import type { RetryFromFailurePreview, RetryPlanPoint } from './retryFromFailure'
import styles from './RetryFromFailureSidePanel.module.css'

export type RetryScopeMode = 'all' | 'selected'

export function SanitizedOutputAlert({ warning }: Readonly<{ warning: string | undefined }>) {
  if (!warning) return null
  return (
    <StackItem>
      <Alert
        isInline
        variant="warning"
        title="Retry plan updated"
        component="h3"
        data-testid="retry-sanitized-output-alert"
      >
        {warning}
      </Alert>
    </StackItem>
  )
}

type RetryPlanProps = Readonly<{
  defaultPreview: RetryFromFailurePreview | undefined
  defaultIsLoading: boolean
  defaultIsError: boolean
  activePreview: RetryFromFailurePreview | undefined
  activeIsLoading: boolean
  activeIsError: boolean
  defaultPoints: RetryPlanPoint[]
  selectablePoints: RetryPlanPoint[]
  visiblePoints: RetryPlanPoint[]
  unavailablePoints: RetryPlanPoint[]
  requestedRetryPointIds: string[]
  selectedPointCount: number
  notRetriedFailureCount: number
  scopeMode: RetryScopeMode
  scopeId: string
  isRetryPending: boolean
  onSelectAll: () => void
  onChoosePoints: () => void
  onUpdatePoint: (pointId: string, isChecked: boolean) => void
}>

type RetryPlanContentProps = Readonly<{
  preview: RetryFromFailurePreview | undefined
  isLoading: boolean
  isError: boolean
  isEmptySelection: boolean
  visiblePoints: RetryPlanPoint[]
  unavailablePoints: RetryPlanPoint[]
  scopeMode: RetryScopeMode
  selectedPointCount: number
  affectedPointCount: number
  notRetriedFailureCount: number
}>

/** Retry scope controls and the stateful retry plan view. */
export function RetryPlan({
  defaultPreview,
  defaultIsLoading,
  defaultIsError,
  activePreview,
  activeIsLoading,
  activeIsError,
  defaultPoints,
  selectablePoints,
  visiblePoints,
  unavailablePoints,
  requestedRetryPointIds,
  selectedPointCount,
  notRetriedFailureCount,
  scopeMode,
  scopeId,
  isRetryPending,
  onSelectAll,
  onChoosePoints,
  onUpdatePoint,
}: RetryPlanProps) {
  if (defaultIsLoading) {
    return (
      <Content component={ContentVariants.p}>
        <Spinner size="md" aria-label="Loading retry plan" /> Checking which steps will run again…
      </Content>
    )
  }

  if (defaultIsError) {
    return (
      <Alert isInline variant="danger" title="Could not load retry plan" data-testid="retry-preview-error">
        The retry plan could not be loaded. Close this panel and try again.
      </Alert>
    )
  }

  if (defaultPreview && !defaultPreview.eligible) {
    return (
      <Alert isInline variant="warning" title="This run cannot be retried from failure" data-testid="retry-rejected">
        {defaultPreview.reason ?? 'No failed steps were found to retry from.'}
      </Alert>
    )
  }

  if (!defaultPreview || defaultPoints.length === 0) {
    return (
      <Alert isInline variant="warning" title="No retry points found" data-testid="retry-no-points">
        No failed steps were found to retry from.
      </Alert>
    )
  }

  return (
    <Stack hasGutter>
      {selectablePoints.length > 1 && (
        <StackItem>
          <RetryScopeSelector
            scopeMode={scopeMode}
            scopeId={scopeId}
            selectablePoints={selectablePoints}
            selectedPointIds={requestedRetryPointIds}
            affectedPointCount={selectablePoints.length}
            isRetryPending={isRetryPending}
            onSelectAll={onSelectAll}
            onChoosePoints={onChoosePoints}
            onUpdatePoint={onUpdatePoint}
          />
        </StackItem>
      )}
      <StackItem>
        <RetryPlanContent
          preview={activePreview}
          isLoading={activeIsLoading}
          isError={activeIsError}
          isEmptySelection={scopeMode === 'selected' && requestedRetryPointIds.length === 0}
          visiblePoints={visiblePoints}
          unavailablePoints={unavailablePoints}
          scopeMode={scopeMode}
          selectedPointCount={selectedPointCount}
          affectedPointCount={selectablePoints.length}
          notRetriedFailureCount={notRetriedFailureCount}
        />
      </StackItem>
    </Stack>
  )
}

type RetryScopeSelectorProps = Readonly<{
  scopeMode: RetryScopeMode
  scopeId: string
  selectablePoints: RetryPlanPoint[]
  selectedPointIds: string[]
  affectedPointCount: number
  isRetryPending: boolean
  onSelectAll: () => void
  onChoosePoints: () => void
  onUpdatePoint: (pointId: string, isChecked: boolean) => void
}>

function RetryScopeSelector({
  scopeMode,
  scopeId,
  selectablePoints,
  selectedPointIds,
  affectedPointCount,
  isRetryPending,
  onSelectAll,
  onChoosePoints,
  onUpdatePoint,
}: RetryScopeSelectorProps) {
  return (
    <Stack hasGutter>
      <StackItem>
        <div role="radiogroup" aria-label="Retry scope" className={styles.scopeOptions}>
          <Radio
            id={`${scopeId}-all`}
            name={`${scopeId}-scope`}
            label="Retry all affected branches"
            isChecked={scopeMode === 'all'}
            isDisabled={isRetryPending}
            onChange={onSelectAll}
          />
          <Radio
            id={`${scopeId}-selected`}
            name={`${scopeId}-scope`}
            label="Choose branches"
            isChecked={scopeMode === 'selected'}
            isDisabled={isRetryPending}
            onChange={onChoosePoints}
          />
        </div>
      </StackItem>
      {scopeMode === 'selected' && (
        <StackItem>
          <Stack hasGutter>
            <StackItem>
              <Title headingLevel="h4" size={TitleSizes.md}>
                Select the branches where the retry should begin
              </Title>
            </StackItem>
            <StackItem>
              <div role="group" aria-label="Branches to retry">
                <List isPlain>
                  {selectablePoints.map((point) => (
                    <ListItem key={point.id}>
                      <Checkbox
                        id={`${scopeId}-${point.id}`}
                        name={`${scopeId}-retry-points`}
                        label={point.name}
                        description={point.typeLabel}
                        body={
                          point.sanitizedFailedNodeNames.length > 0 ? (
                            <div className={styles.sanitizedReplacementDescription}>
                              {point.sanitizedFailedNodeNames.map((failedNodeName) => (
                                <div key={failedNodeName}>Failed node: {failedNodeName}</div>
                              ))}
                              <div>Output sanitized — retry starts upstream</div>
                            </div>
                          ) : undefined
                        }
                        isChecked={selectedPointIds.includes(point.id)}
                        isDisabled={isRetryPending}
                        onChange={(_event, isChecked) => onUpdatePoint(point.id, isChecked)}
                      />
                    </ListItem>
                  ))}
                </List>
              </div>
            </StackItem>
            {selectedPointIds.length > 0 && selectedPointIds.length < affectedPointCount && (
              <StackItem>
                <Alert
                  isInline
                  variant="warning"
                  title="Some branches may fail"
                  data-testid="retry-partial-scope-warning"
                >
                  Skipped branches may leave downstream dependencies or the merge step without the inputs they need.
                </Alert>
              </StackItem>
            )}
          </Stack>
        </StackItem>
      )}
    </Stack>
  )
}

function RetryPlanContent({
  preview,
  isLoading,
  isError,
  isEmptySelection,
  visiblePoints,
  unavailablePoints,
  scopeMode,
  selectedPointCount,
  affectedPointCount,
  notRetriedFailureCount,
}: RetryPlanContentProps) {
  if (isEmptySelection) {
    return (
      <Alert isInline variant="info" title="Choose at least one failure point">
        Select one or more failed steps to see the retry plan for that selection.
      </Alert>
    )
  }

  if (isLoading) {
    return (
      <Content component={ContentVariants.p}>
        <Spinner size="sm" aria-label="Updating selected retry plan" /> Updating the plan for this selection…
      </Content>
    )
  }

  if (isError) {
    return (
      <Alert isInline variant="danger" title="Could not update retry plan" data-testid="retry-preview-error">
        The retry plan could not be updated. Change the selection or close and reopen this panel.
      </Alert>
    )
  }

  if (!preview) {
    return (
      <Alert isInline variant="info" title="Choose at least one failure point">
        Select one or more failed steps to see the retry plan for that selection.
      </Alert>
    )
  }

  if (!preview.eligible) {
    return (
      <Alert isInline variant="warning" title="This retry selection cannot be used" data-testid="retry-rejected">
        {preview.reason ?? 'The selected failure points cannot be retried.'}
      </Alert>
    )
  }

  if (visiblePoints.length === 0) {
    return (
      <Alert isInline variant="warning" title="No retry points found" data-testid="retry-no-points">
        No failed steps were found to retry from.
      </Alert>
    )
  }

  return (
    <RetryPlanSummary
      preview={preview}
      visiblePoints={visiblePoints}
      unavailablePoints={unavailablePoints}
      scopeMode={scopeMode}
      selectedPointCount={selectedPointCount}
      affectedPointCount={affectedPointCount}
      notRetriedFailureCount={notRetriedFailureCount}
    />
  )
}

type RetryPlanSummaryProps = Readonly<{
  preview: RetryFromFailurePreview
  visiblePoints: RetryPlanPoint[]
  unavailablePoints: RetryPlanPoint[]
  scopeMode: RetryScopeMode
  selectedPointCount: number
  affectedPointCount: number
  notRetriedFailureCount: number
}>

function RetryPlanSummary({
  preview,
  visiblePoints,
  unavailablePoints,
  scopeMode,
  selectedPointCount,
  affectedPointCount,
  notRetriedFailureCount,
}: RetryPlanSummaryProps) {
  return (
    <DescriptionList isHorizontal isCompact aria-label="Retry plan summary">
      {scopeMode === 'selected' && selectedPointCount > 0 && (
        <DescriptionListGroup>
          <DescriptionListTerm>Scope</DescriptionListTerm>
          <DescriptionListDescription>
            {selectedPointCount} of {affectedPointCount} affected branches selected
          </DescriptionListDescription>
        </DescriptionListGroup>
      )}
      <DescriptionListGroup>
        <DescriptionListTerm>Steps to retry</DescriptionListTerm>
        <DescriptionListDescription>
          <div>
            <div>{getRetryStepCountLabel(preview.total_step_count)}</div>
            <Content component={ContentVariants.small}>Includes affected steps and any downstream merge step</Content>
          </div>
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Retry starts at</DescriptionListTerm>
        <DescriptionListDescription>
          <div data-testid="retry-starts-at">
            {visiblePoints.length === 1 ? (
              <RetryPlanPointLabel point={visiblePoints[0]} />
            ) : (
              <List isPlain aria-label="Failure points included in the retry">
                {visiblePoints.map((point) => (
                  <ListItem key={point.id}>
                    <RetryPlanPointLabel point={point} />
                  </ListItem>
                ))}
              </List>
            )}
          </div>
        </DescriptionListDescription>
      </DescriptionListGroup>
      {unavailablePoints.length > 0 && (
        <DescriptionListGroup>
          <DescriptionListTerm>Unavailable output</DescriptionListTerm>
          <DescriptionListDescription>
            <div data-testid="retry-unavailable-output">
              {unavailablePoints.length === 1 ? (
                <strong>{unavailablePoints[0].name}</strong>
              ) : (
                <List isPlain aria-label="Steps with sanitized output">
                  {unavailablePoints.map((point) => (
                    <ListItem key={point.id}>
                      <strong>{point.name}</strong>
                    </ListItem>
                  ))}
                </List>
              )}
              <Content component={ContentVariants.small}>Sanitized for safety and regenerated during retry</Content>
            </div>
          </DescriptionListDescription>
        </DescriptionListGroup>
      )}
      <DescriptionListGroup>
        <DescriptionListTerm>Retained results</DescriptionListTerm>
        <DescriptionListDescription>{getRetainedResultLabel(preview.retained_result_count)}</DescriptionListDescription>
      </DescriptionListGroup>
      {scopeMode === 'selected' && selectedPointCount > 0 && notRetriedFailureCount > 0 && (
        <DescriptionListGroup>
          <DescriptionListTerm>Not retried</DescriptionListTerm>
          <DescriptionListDescription>{getNotRetriedFailureLabel(notRetriedFailureCount)}</DescriptionListDescription>
        </DescriptionListGroup>
      )}
    </DescriptionList>
  )
}

function RetryPlanPointLabel({ point }: Readonly<{ point: RetryPlanPoint }>) {
  return (
    <div className={styles.retryPoint}>
      <strong>{point.name}</strong>
      <Content component={ContentVariants.small}>{point.typeLabel}</Content>
    </div>
  )
}

function getRetainedResultLabel(count: number | undefined): string {
  if (count === undefined) return '—'
  return `${count} completed ${count === 1 ? 'result' : 'results'} retained`
}

function getNotRetriedFailureLabel(count: number): string {
  return `${count} failed ${count === 1 ? 'step remains' : 'steps remain'} failed`
}

function getRetryStepCountLabel(count: number | undefined): string {
  if (count === undefined) return 'The number of steps to retry is unavailable.'
  return `${count} ${count === 1 ? 'step' : 'steps'} will be retried`
}

export function HowRetryWorks() {
  return (
    <>
      <Title className={styles.sectionTitle} headingLevel="h3" size={TitleSizes.md}>
        How retry works
      </Title>
      <Stack hasGutter>
        <StackItem>
          <Content component={ContentVariants.p}>
            This retry uses the same workflow version as this run, preserving the definition that ran. Nodes outside the
            selected retry scope will not re-execute. Completed nodes retain their previous result, failed nodes remain
            failed, and nodes that did not run remain skipped. Nodes in the selected scope will be retried and may
            repeat external side effects.
          </Content>
        </StackItem>
        <StackItem>
          <Content component={ContentVariants.p}>
            To change the parameters for this retry, select the failed node in Run details and choose Edit parameters
            for retry.
          </Content>
        </StackItem>
      </Stack>
    </>
  )
}

type RetryFooterProps = Readonly<{
  onRetry: () => void
  onCancel: () => void
  isRetryDisabled: boolean
  isRetryPending: boolean
  stepCount?: number
}>

export function RetryFooter({ onRetry, onCancel, isRetryDisabled, isRetryPending, stepCount }: RetryFooterProps) {
  return (
    <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
      <FlexItem>
        <Button
          variant="primary"
          onClick={onRetry}
          isLoading={isRetryPending}
          isDisabled={isRetryDisabled}
          data-testid="retry-from-failure-confirm"
        >
          {getRetryButtonLabel(stepCount)}
        </Button>
      </FlexItem>
      <FlexItem>
        <Button variant="link" onClick={onCancel} isDisabled={isRetryPending}>
          Cancel
        </Button>
      </FlexItem>
    </Flex>
  )
}

function getRetryButtonLabel(stepCount: number | undefined): string {
  if (stepCount === undefined) return 'Retry run from failure'
  const stepLabel = stepCount === 1 ? 'step' : 'steps'
  return `Retry ${stepCount} ${stepLabel}`
}
