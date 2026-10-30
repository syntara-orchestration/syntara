import {
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Stack,
  StackItem,
  Tab,
  Tabs,
  TabTitleText,
  Title,
  TitleSizes,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import type { ExecutionsAPI } from '@syntara/contracts'
import type React from 'react'

import { ApprovalPendingBadge } from '../../components/labels/ApprovalPendingBadge'
import { SynPanel } from '../../components/layout/SynPanel'
import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'

import { StatusLabel } from './ExecutionStatus'

export type ViewMode = 'overview' | 'details'

type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']

type HeaderMetadataProps = {
  execution: {
    started_at?: string | null
    created_at?: string | null
    completed_at?: string | null
    status?: ExecutionStatus | null
    approval_pending?: boolean
  }
  elapsedLabel?: string
  isRunning: boolean
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
  headerLabel?: string
  onClosePanel?: () => void
}

export function HeaderMetadata({
  execution,
  elapsedLabel,
  isRunning,
  viewMode,
  onViewModeChange,
  headerLabel,
  onClosePanel,
}: Readonly<HeaderMetadataProps>) {
  const startDisplay = execution.started_at ?? execution.created_at

  const title = headerLabel ?? (isRunning ? 'Current run details' : 'Run details')

  return (
    <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
      <FlexItem>
        <Flex gap={{ default: 'gapLg' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <Title headingLevel="h2" size={TitleSizes.md} style={{ margin: 0 }}>
              {title}
            </Title>
          </FlexItem>
          <FlexItem>
            <Tabs activeKey={viewMode} onSelect={(_e, key) => onViewModeChange(key as ViewMode)} variant="secondary">
              <Tab eventKey="overview" title={<TabTitleText>Overview</TabTitleText>} />
              <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
            </Tabs>
          </FlexItem>
        </Flex>
      </FlexItem>
      <FlexItem>
        <Flex gap={{ default: 'gapMd' }} alignItems={{ default: 'alignItemsCenter' }}>
          {startDisplay && (
            <Content
              component={ContentVariants.small}
              style={{ color: 'var(--pf-t--global--text--color--subtle)', margin: 0 }}
            >
              <ExecutionTimestamp dateString={startDisplay} />
              {execution.completed_at && (
                <>
                  {' - '}
                  <ExecutionTimestamp dateString={execution.completed_at} />
                </>
              )}
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
          {execution.status && (
            <FlexItem>
              <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
                <FlexItem>
                  <StatusLabel status={execution.status} />
                </FlexItem>
                {execution.approval_pending && (
                  <FlexItem>
                    <ApprovalPendingBadge approvalPending={execution.approval_pending} />
                  </FlexItem>
                )}
              </Flex>
            </FlexItem>
          )}
          {onClosePanel && (
            <FlexItem>
              <Button
                variant="plain"
                aria-label="Close run details panel"
                onClick={onClosePanel}
                icon={<RhUiCloseIcon />}
              />
            </FlexItem>
          )}
        </Flex>
      </FlexItem>
    </Flex>
  )
}

export function NoSelectionState() {
  return (
    <Flex
      justifyContent={{ default: 'justifyContentCenter' }}
      alignItems={{ default: 'alignItemsCenter' }}
      style={{ height: '100%' }}
    >
      <Content component={ContentVariants.p} style={{ color: 'var(--pf-t--global--text--color--subtle)' }}>
        Select a step from the list or canvas to view its input and output data.
      </Content>
    </Flex>
  )
}

export function LoadingErrorState({ queryState }: Readonly<{ queryState: React.ReactNode }>) {
  return (
    <SynPanel
      style={{
        height: '100%',
        maxHeight: '100%',
        width: '24rem',
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Stack>
        <StackItem style={{ padding: 'var(--pf-t--global--spacer--lg)' }}>
          <Title headingLevel="h2" size={TitleSizes.lg}>
            Current run details
          </Title>
        </StackItem>
        <StackItem isFilled style={{ padding: 'var(--pf-t--global--spacer--lg)' }}>
          {queryState}
        </StackItem>
      </Stack>
    </SynPanel>
  )
}
