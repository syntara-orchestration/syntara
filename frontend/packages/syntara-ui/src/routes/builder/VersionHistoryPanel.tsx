import {
  Button,
  Content,
  ContentVariants,
  Divider,
  Flex,
  FlexItem,
  Icon,
  SimpleList,
  SimpleListGroup,
  Stack,
  StackItem,
  Title,
  TitleSizes,
} from '@patternfly/react-core'
import { RhUiClockIcon, RhUiCloseIcon } from '@patternfly/react-icons'
import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { MultiSelectFilter } from '../../components/filters/MultiSelectFilter'
import pageMainSlotStyles from '../../components/layout/SynPage.module.css'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynEmptyStateFilter } from '../../components/states/SynEmptyStateFilter'
import type { PaginationFooterProps } from '../../components/table/PaginationFooter'
import { PaginationFooter } from '../../components/table/PaginationFooter'
import type { FilterConfig } from '../../types/filters'

import { getDateGroupLabel } from './historyDateUtils'
import { nextOpenKebabVersionId } from './hooks/versionHistoryHelpers'
import styles from './VersionHistoryPanel.module.css'
import { VersionRow } from './VersionHistoryRow'
import { type VersionStatus } from './VersionStatusBadge'

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

type VersionGroup = {
  label: string
  items: WorkflowVersion[]
}

type VersionHistoryPanelProps = Readonly<{
  versions: WorkflowVersion[]
  onClose: () => void
  onSelectVersion: (version: number) => void
  onRestoreVersion: (version: number, createdAt: string) => void
  onExportVersion: (version: number) => void
  onOpenInNewWindow: (version: number) => void
  onPublishVersion: (version: number) => void
  onViewRunHistory: (versionNumber: number) => void
  executedVersionNumbers: Map<number, string>
  onEditVersion: (version: WorkflowVersion) => void
  onDuplicateVersion: (version: WorkflowVersion) => void
  statusFilter: VersionStatus[]
  onStatusFilterChange: (statuses: VersionStatus[]) => void
  selectedVersion?: number | null
  canEdit?: boolean
  editTooltip?: string
  canCreate?: boolean
  createTooltip?: string
  projectId?: string
  publishedVersionName?: string | null
  paginationFooterProps?: PaginationFooterProps
}>

const STATUS_FILTER_OPTIONS: { label: string; value: string }[] = [
  { label: 'Published', value: 'published' },
  { label: 'Previously published', value: 'previously_published' },
]

function groupVersionsByDate(versions: WorkflowVersion[]): VersionGroup[] {
  const map = new Map<string, WorkflowVersion[]>()
  for (const version of versions) {
    const label = version.created_at ? getDateGroupLabel(version.created_at) : 'Unknown'
    if (!map.has(label)) map.set(label, [])
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- safe: the key was just inserted above
    map.get(label)!.push(version)
  }
  return Array.from(map.entries()).map(([label, items]) => ({ label, items }))
}

export function VersionHistoryPanel(props: VersionHistoryPanelProps) {
  const {
    versions,
    onClose,
    onSelectVersion,
    onRestoreVersion,
    onExportVersion,
    onOpenInNewWindow,
    onPublishVersion,
    onViewRunHistory,
    executedVersionNumbers,
    onEditVersion,
    onDuplicateVersion,
    statusFilter,
    onStatusFilterChange,
    selectedVersion,
    canEdit = true,
    editTooltip,
    canCreate = canEdit,
    createTooltip,
    projectId,
    publishedVersionName,
    paginationFooterProps,
  } = props

  const groups = useMemo(() => groupVersionsByDate(versions), [versions])
  const [openKebabVersionId, setOpenKebabVersionId] = useState<string | null>(null)
  const selectedRef = useRef<HTMLSpanElement>(null)
  const scrollToSelected = useCallback(() => {
    const li = selectedRef.current?.closest('li')
    li?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [])
  useEffect(scrollToSelected, [selectedVersion, scrollToSelected])

  let listBody: ReactNode
  if (versions.length === 0 && statusFilter.length > 0) {
    listBody = <SynEmptyStateFilter clearAllFilters={() => onStatusFilterChange([])} />
  } else if (versions.length === 0) {
    listBody = (
      <Content component={ContentVariants.p} className={styles.emptyStateText}>
        No version history available
      </Content>
    )
  } else {
    listBody = (
      <SimpleList isControlled={false} aria-label="Version history list" className={styles.simpleList}>
        {groups.map(({ label, items }) => (
          <SimpleListGroup
            key={label}
            title={
              <Content component={ContentVariants.small} className={styles.groupTitle}>
                {label}
              </Content>
            }
          >
            {items.flatMap((version) => {
              const isActive = selectedVersion === version.version
              return [
                <VersionRow
                  key={version.id}
                  version={version}
                  onSelect={() => onSelectVersion(version.version)}
                  onRestore={() => onRestoreVersion(version.version, version.created_at)}
                  onExport={() => onExportVersion(version.version)}
                  onOpenInNewWindow={() => onOpenInNewWindow(version.version)}
                  onPublish={() => onPublishVersion(version.version)}
                  onViewRunHistory={() => onViewRunHistory(version.version)}
                  hasRunHistory={executedVersionNumbers.has(version.version)}
                  onEdit={() => onEditVersion(version)}
                  onDuplicate={() => onDuplicateVersion(version)}
                  canCreate={canCreate}
                  createTooltip={createTooltip}
                  projectId={projectId}
                  isSelected={isActive}
                  isKebabOpen={openKebabVersionId === version.id}
                  onKebabToggle={() => setOpenKebabVersionId(nextOpenKebabVersionId(openKebabVersionId, version.id))}
                  onKebabClose={() => setOpenKebabVersionId(null)}
                  canEdit={canEdit}
                  editTooltip={editTooltip}
                  scrollRef={isActive ? selectedRef : undefined}
                />,
                <Divider key={`${version.id}-divider`} component="li" />,
              ]
            })}
          </SimpleListGroup>
        ))}
      </SimpleList>
    )
  }

  return (
    <SynPanel hasNoPadding isFullHeight className={styles.panelRoot}>
      <div className={styles.panelInner}>
        <Stack className={styles.panelStack}>
          <StackItem className={styles.panelHeader}>
            <Flex
              justifyContent={{ default: 'justifyContentSpaceBetween' }}
              alignItems={{ default: 'alignItemsFlexStart' }}
            >
              <FlexItem>
                <Stack hasGutter>
                  <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
                    <Icon>
                      <RhUiClockIcon />
                    </Icon>
                    <Title headingLevel="h2" size={TitleSizes.md}>
                      Version history
                    </Title>
                  </Flex>
                  <Content component={ContentVariants.small}>Browse past saves and publishes.</Content>
                </Stack>
              </FlexItem>
              <FlexItem>
                <Button variant="plain" onClick={onClose} aria-label="Close version history">
                  <Icon>
                    <RhUiCloseIcon />
                  </Icon>
                </Button>
              </FlexItem>
            </Flex>
          </StackItem>

          {(versions.length > 0 || statusFilter.length > 0) && (
            <StackItem className={styles.filterSection}>
              <MultiSelectFilter
                fieldKey="status"
                label="State"
                options={STATUS_FILTER_OPTIONS}
                selectedValues={statusFilter}
                placeholder="Filter by state"
                onChange={(filter: FilterConfig | null) => {
                  onStatusFilterChange(filter ? (filter.value as VersionStatus[]) : [])
                }}
              />
            </StackItem>
          )}

          {publishedVersionName && (
            <StackItem className={styles.filterSection}>
              <Content component={ContentVariants.small}>
                Currently published:{' '}
                <Button variant="link" isInline onClick={() => onStatusFilterChange(['published'] as VersionStatus[])}>
                  {publishedVersionName}
                </Button>
              </Content>
            </StackItem>
          )}

          <StackItem isFilled className={`${pageMainSlotStyles.main} ${styles.scrollableBody}`}>
            {listBody}
          </StackItem>

          {paginationFooterProps && (
            <StackItem className={styles.paginationFooter}>
              <PaginationFooter {...paginationFooterProps} />
            </StackItem>
          )}
        </Stack>
      </div>
    </SynPanel>
  )
}
