import {
  Button,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  Stack,
  StackItem,
  Title,
} from '@patternfly/react-core'
import { RhUiArrowLeftIcon, RhUiSearchIcon, RhUiSyncIcon } from '@patternfly/react-icons'
import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { useNavigate, useParams } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { AppRoute } from '../../app/AppRoute'
import {
  breadcrumbsExecutionTargetDetail,
  breadcrumbsExecutionTargetDetailEarlyShell,
} from '../../app/breadcrumbBuilders'
import { executionPlaneClient } from '../../client'
import { SynDetail } from '../../components/details/SynDetail'
import { SynDetailList } from '../../components/details/SynDetailList'
import { SynLabel } from '../../components/labels/SynLabel'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynPanelContentStack } from '../../components/layout/SynPanelContentStack'
import { SynErrorState } from '../../components/states/SynErrorState'
import { useQueryState } from '../../components/states/useQueryState'
import { SynLink } from '../../components/SynLink'
import { SynPageTitle } from '../../components/SynPageTitle'
import { getErrorStatus } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import { ExecutionTargetStatusLabel } from './ExecutionTargetStatusLabel'
import { getNodeSelectors } from './getNodeSelectors'
import { NodeSelectorsCell } from './NodeSelectorsCell'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetFacadeRead']

function ExecutionTargetDetailEarlyShell({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <SynPage>
      <SynPageTitle segments={['Execution target', 'Execution Plane']} />
      <SynPageHeader title="Execution target" breadcrumbs={breadcrumbsExecutionTargetDetailEarlyShell()} />
      <SynPageBody>
        <SynPanel isFullHeight>{children}</SynPanel>
      </SynPageBody>
    </SynPage>
  )
}

function ClusterDetailValue({ target }: Readonly<{ target: ExecutionTarget }>) {
  const integrationId = target.labels?.integration_id?.trim() || undefined
  const displayId = target.cluster_id || '—'

  if (!integrationId) {
    return <>{displayId}</>
  }

  return (
    <SynLink to={AppRoute.Configuration.Integrations.Detail.replace(':integrationId', integrationId)}>
      {displayId}
    </SynLink>
  )
}

function ExecutionTargetDetailsBody({ target }: Readonly<{ target: ExecutionTarget }>) {
  const placement = target.placement
  const namespace = placement?.type === 'kubernetes' && placement.namespace ? placement.namespace : null
  const nodeSelectors = getNodeSelectors(placement)

  return (
    <SynPanelContentStack hasGutter>
      <StackItem>
        <Stack hasGutter>
          <StackItem>
            <Title headingLevel="h2" size="lg">
              General
            </Title>
          </StackItem>
          <StackItem>
            <SynDetailList isHorizontal>
              <SynDetail label="Name">{target.name}</SynDetail>
              <SynDetail label="OpenShift Cluster">
                <ClusterDetailValue target={target} />
              </SynDetail>
              <SynDetail label="Execution namespace">{namespace ?? '—'}</SynDetail>
              <SynDetail label="State">
                <SynLabel status={target.enabled ? 'success' : 'custom'}>
                  {target.enabled ? 'Enabled' : 'Disabled'}
                </SynLabel>
              </SynDetail>
              <SynDetail label="Status">
                <ExecutionTargetStatusLabel status={target.status} message={target.status_message} />
              </SynDetail>
            </SynDetailList>
          </StackItem>
        </Stack>
      </StackItem>
      <StackItem>
        <Stack hasGutter>
          <StackItem>
            <Title headingLevel="h2" size="lg">
              Routing
            </Title>
          </StackItem>
          <StackItem>
            <SynDetailList isHorizontal>
              <SynDetail label="OpenShift node selector">
                <NodeSelectorsCell selectors={nodeSelectors} />
              </SynDetail>
            </SynDetailList>
          </StackItem>
        </Stack>
      </StackItem>
    </SynPanelContentStack>
  )
}

function ExecutionTargetNotFound({ onRetry, onBack }: Readonly<{ onRetry: () => void; onBack: () => void }>) {
  return (
    <EmptyState headingLevel="h2" titleText="Execution target not found" icon={RhUiSearchIcon} isFullHeight>
      <EmptyStateBody>The execution target you are looking for does not exist or may have been deleted.</EmptyStateBody>
      <EmptyStateFooter>
        <EmptyStateActions>
          <Button variant="primary" icon={<RhUiArrowLeftIcon />} onClick={onBack}>
            Back to Execution Plane
          </Button>
          <Button variant="link" icon={<RhUiSyncIcon />} onClick={onRetry}>
            Retry
          </Button>
        </EmptyStateActions>
      </EmptyStateFooter>
    </EmptyState>
  )
}

export default function ExecutionTargetDetail() {
  const { executionTargetId }: { executionTargetId?: string } = useParams({ strict: false })
  const navigate = useNavigate()
  const docLink = useDocLink('executionPlane')
  const hasId = Boolean(executionTargetId?.length)

  const query = executionPlaneClient.useQuery(
    'get',
    '/api/execution_plane/v1/execution_targets/{target_id}',
    {
      params: { path: { target_id: executionTargetId ?? '' } },
    },
    { enabled: hasId, refetchInterval: 30_000 }
  )

  const target = query.data
  const queryState = useQueryState(query, {
    title: 'Error loading execution target',
    onRetry: () => detachPromise(query.refetch()),
  })

  const navigateBack = () => detachPromise(navigate({ to: AppRoute.ExecutionPlane.Root }))
  const retry = () => detachPromise(query.refetch())

  if (!hasId) {
    return (
      <ExecutionTargetDetailEarlyShell>
        <SynErrorState title="Invalid execution target" message="No execution target ID provided" />
      </ExecutionTargetDetailEarlyShell>
    )
  }

  // Domain-specific empty state for missing targets; useQueryState handles other errors.
  if (getErrorStatus(query.error) === 404) {
    return (
      <ExecutionTargetDetailEarlyShell>
        <ExecutionTargetNotFound onRetry={retry} onBack={navigateBack} />
      </ExecutionTargetDetailEarlyShell>
    )
  }

  if (queryState) {
    return <ExecutionTargetDetailEarlyShell>{queryState}</ExecutionTargetDetailEarlyShell>
  }

  if (!target) {
    return null
  }

  return (
    <SynPage>
      <SynPageTitle segments={[target.name, 'Execution Plane']} />
      <SynPageHeader
        breadcrumbs={breadcrumbsExecutionTargetDetail(target.name)}
        title={target.name}
        docLink={docLink}
      />
      <SynPageBody>
        <SynPanel isFullHeight isScrollable>
          <ExecutionTargetDetailsBody target={target} />
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
