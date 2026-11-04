import {
  Content,
  ContentVariants,
  Dropdown,
  DropdownGroup,
  DropdownItem,
  DropdownList,
  Divider,
  FlexItem,
  MenuToggle,
  type MenuToggleElement,
  Stack,
  Tooltip,
} from '@patternfly/react-core'
import {
  RhUiDuplicateIcon,
  RhUiEditIcon,
  RhUiEllipsisVerticalFillIcon,
  RhUiExportIcon,
  RhUiExternalLinkIcon,
  RhUiHistoryIcon,
  RhUiPublishIcon,
  RhUiUndoIcon,
} from '@patternfly/react-icons'
import type { WorkflowAPI } from '@syntara/contracts'
import { useMemo, type ReactNode, type Ref } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { SynLink } from '../../components/SynLink'
import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { detachPromise } from '../../utils/detachPromise'
import { toLinkedUserId, toUserReferenceName } from '../../utils/userReference'
import {
  getStepTypePermissionMessage,
  getStepTypesFromDefinition,
  useStepTypePermissions,
} from '../workflows/useStepTypePermissions'

import { formatHistoryDateTime } from './historyDateUtils'
import { resolveVersionStatusForBadge, shouldShowSecondaryVersionDatetime } from './hooks/historyRowModel'
import { closeWhenDropdownCloses } from './hooks/versionHistoryHelpers'
import styles from './VersionHistoryPanel.module.css'
import { VersionStatusBadge } from './VersionStatusBadge'

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

type VersionKebabToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isOpen: boolean
  onToggle: () => void
  ariaLabel: string
}>

function VersionKebabToggle({ toggleRef, isOpen, onToggle, ariaLabel }: VersionKebabToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      variant="plain"
      onClick={(e) => {
        e.stopPropagation()
        onToggle()
      }}
      isExpanded={isOpen}
      aria-label={ariaLabel}
    >
      <RhUiEllipsisVerticalFillIcon />
    </MenuToggle>
  )
}

type VersionKebabMenuProps = Readonly<{
  version: WorkflowVersion
  isOpen: boolean
  onToggle: () => void
  onClose: () => void
  onRestore: () => void
  onExport: () => void
  onOpenInNewWindow: () => void
  onPublish: () => void
  onViewRunHistory: () => void
  hasRunHistory: boolean
  onEdit: () => void
  onDuplicate: () => void
  onRetryPermissionCheck?: () => void
  permissionCheckError?: boolean
  canEdit: boolean
  canDuplicate: boolean
  editTooltip?: string
  duplicateTooltip?: string
}>

function actionIfAllowed(isAllowed: boolean, action: () => void): (() => void) | undefined {
  return isAllowed ? action : undefined
}

function getDisabledTooltip(isDisabled: boolean, content?: string) {
  return isDisabled && content ? { content } : undefined
}

function getPublishTooltip(disabledTooltip: { content: string } | undefined, isAlreadyPublished: boolean) {
  if (disabledTooltip) return disabledTooltip
  if (isAlreadyPublished) return { content: 'This version is already published' }
  return undefined
}

function VersionKebabMenu({
  version,
  isOpen,
  onToggle,
  onClose,
  onRestore,
  onExport,
  onOpenInNewWindow,
  onPublish,
  onViewRunHistory,
  hasRunHistory,
  onEdit,
  onDuplicate,
  onRetryPermissionCheck,
  permissionCheckError,
  canEdit,
  canDuplicate,
  editTooltip,
  duplicateTooltip,
}: VersionKebabMenuProps) {
  const ariaLabel = `Actions for version ${version.version}`
  const disabledTooltip = getDisabledTooltip(!canEdit, editTooltip)
  const duplicateDisabledTooltip = getDisabledTooltip(!canDuplicate, duplicateTooltip ?? editTooltip)
  const isAlreadyPublished = version.status === 'published'
  const publishTooltip = getPublishTooltip(disabledTooltip, isAlreadyPublished)
  const renderToggle = (toggleRef: Ref<MenuToggleElement>) => (
    <VersionKebabToggle toggleRef={toggleRef} isOpen={isOpen} onToggle={onToggle} ariaLabel={ariaLabel} />
  )

  return (
    <Dropdown
      isOpen={isOpen}
      onSelect={onClose}
      onOpenChange={(open) => closeWhenDropdownCloses(open, onClose)}
      toggle={renderToggle}
      popperProps={{ position: 'end' }}
    >
      <DropdownGroup label="Views">
        <DropdownList>
          <DropdownItem key="open-new-window" onClick={() => onOpenInNewWindow()} icon={<RhUiExternalLinkIcon />}>
            Open version in new window
          </DropdownItem>
          <DropdownItem
            key="view-run-history"
            onClick={actionIfAllowed(hasRunHistory, onViewRunHistory)}
            icon={<RhUiHistoryIcon />}
            isAriaDisabled={!hasRunHistory}
            tooltipProps={!hasRunHistory ? { content: 'No runs for this version' } : undefined}
          >
            View run history of this version
          </DropdownItem>
        </DropdownList>
      </DropdownGroup>
      {permissionCheckError && (
        <DropdownGroup label="Permission check">
          <DropdownList>
            <DropdownItem key="retry-step-type-permissions" onClick={onRetryPermissionCheck}>
              Retry step-type permission check
            </DropdownItem>
          </DropdownList>
        </DropdownGroup>
      )}
      <Divider />
      <DropdownGroup label="Actions">
        <DropdownList>
          <DropdownItem
            key="restore"
            onClick={actionIfAllowed(canEdit, onRestore)}
            icon={<RhUiUndoIcon />}
            isAriaDisabled={!canEdit}
            tooltipProps={disabledTooltip}
          >
            Restore version
          </DropdownItem>
          <DropdownItem
            key="edit"
            onClick={actionIfAllowed(canEdit, onEdit)}
            icon={<RhUiEditIcon />}
            isAriaDisabled={!canEdit}
            tooltipProps={disabledTooltip}
          >
            Edit version name and description
          </DropdownItem>
          <DropdownItem
            key="duplicate"
            onClick={actionIfAllowed(canDuplicate, onDuplicate)}
            icon={<RhUiDuplicateIcon />}
            isAriaDisabled={!canDuplicate}
            tooltipProps={duplicateDisabledTooltip}
          >
            Duplicate as new workflow
          </DropdownItem>
          <DropdownItem key="export" onClick={() => onExport()} icon={<RhUiExportIcon />}>
            Export workflow
          </DropdownItem>
          <DropdownItem
            key="publish"
            onClick={actionIfAllowed(canEdit && !isAlreadyPublished, onPublish)}
            icon={<RhUiPublishIcon />}
            isAriaDisabled={!canEdit || isAlreadyPublished}
            tooltipProps={publishTooltip}
          >
            Publish this version
          </DropdownItem>
        </DropdownList>
      </DropdownGroup>
    </Dropdown>
  )
}

type VersionRowProps = Readonly<{
  version: WorkflowVersion
  onSelect: () => void
  onRestore: () => void
  onExport: () => void
  onOpenInNewWindow: () => void
  onPublish: () => void
  onViewRunHistory: () => void
  hasRunHistory: boolean
  onEdit: () => void
  onDuplicate: () => void
  isSelected?: boolean
  isKebabOpen: boolean
  onKebabToggle: () => void
  onKebabClose: () => void
  canEdit?: boolean
  editTooltip?: string
  canCreate?: boolean
  createTooltip?: string
  projectId?: string
  scrollRef?: Ref<HTMLSpanElement>
}>

function VersionCreatedByLink({ userId, name }: Readonly<{ userId: string; name: string }>) {
  return (
    <SynLink to={AppRoute.AccessManagement.UserDetail.replace(':userId', userId)} className={styles.usernameLink}>
      {name}
    </SynLink>
  )
}

function VersionSecondaryLine({
  createdAt,
  createdBy,
  showDatetime,
}: Readonly<{
  createdAt: WorkflowVersion['created_at']
  createdBy: WorkflowVersion['created_by']
  showDatetime: boolean
}>) {
  const creatorName = toUserReferenceName(createdBy)
  const creatorId = toLinkedUserId(createdBy)
  const datetime = showDatetime && createdAt ? <ExecutionTimestamp dateString={createdAt} /> : null
  if (!datetime && !creatorName) return null

  let creator: ReactNode = null
  if (creatorName) {
    creator = creatorId ? <VersionCreatedByLink userId={creatorId} name={creatorName} /> : creatorName
  }

  return (
    <Content component={ContentVariants.small} className={styles.secondaryDatetime}>
      {datetime}
      {datetime && creator ? ' by ' : null}
      {creator}
    </Content>
  )
}

export function VersionRow({
  version,
  onSelect,
  onRestore,
  onExport,
  onOpenInNewWindow,
  onPublish,
  onViewRunHistory,
  hasRunHistory,
  onEdit,
  onDuplicate,
  isSelected,
  isKebabOpen,
  onKebabToggle,
  onKebabClose,
  canEdit = true,
  editTooltip,
  canCreate = canEdit,
  createTooltip,
  projectId,
  scrollRef,
}: VersionRowProps) {
  const stepTypes = useMemo(
    () => getStepTypesFromDefinition(version.workflow_definition),
    [version.workflow_definition]
  )
  const stepTypePermissions = useStepTypePermissions(stepTypes, projectId, { enabled: isKebabOpen })
  const canEditVersion = canEdit && stepTypePermissions.canAuthor
  const canDuplicateVersion = canCreate && stepTypePermissions.canAuthor
  const stepTypeTooltip = getStepTypePermissionMessage(stepTypePermissions)
  const versionEditTooltip = canEdit ? stepTypeTooltip : editTooltip
  const versionDuplicateTooltip = canCreate ? versionEditTooltip : createTooltip
  const badgeStatus = resolveVersionStatusForBadge(version.status)
  const showSecondaryDatetime = shouldShowSecondaryVersionDatetime(version.name, version.created_at)
  const rowLabel = version.name || formatHistoryDateTime(version.created_at) || `Version ${version.version}`

  return (
    // eslint-disable-next-line syntara/prefer-pf-list-components -- The row-wide click target must remain a sibling of the menu.
    <li className={`pf-v6-c-simple-list__item ${styles.versionRowItem}`}>
      <Tooltip content={rowLabel}>
        <button
          type="button"
          className={`pf-v6-c-simple-list__item-link ${isSelected ? 'pf-m-current' : ''} ${styles.versionRowSelect}`}
          onClick={onSelect}
          data-item-id={version.id}
          aria-label={rowLabel}
          aria-current={isSelected ? 'true' : undefined}
        />
      </Tooltip>
      <span ref={scrollRef} />
      <Stack className={styles.versionRowStack}>
        <FlexItem style={{ minWidth: 0 }}>
          <Content component={ContentVariants.p} className={styles.versionTimestamp}>
            {version.name || <ExecutionTimestamp dateString={version.created_at} />}
          </Content>
        </FlexItem>
        <VersionSecondaryLine
          createdAt={version.created_at}
          createdBy={version.created_by}
          showDatetime={showSecondaryDatetime}
        />
        {badgeStatus && (
          <div className={styles.labelsRow}>
            <VersionStatusBadge status={badgeStatus} />
          </div>
        )}
      </Stack>
      <div className={styles.kebabFlexItem}>
        <VersionKebabMenu
          version={version}
          isOpen={isKebabOpen}
          onToggle={onKebabToggle}
          onClose={onKebabClose}
          onRestore={onRestore}
          onExport={onExport}
          onOpenInNewWindow={onOpenInNewWindow}
          onPublish={onPublish}
          onViewRunHistory={onViewRunHistory}
          hasRunHistory={hasRunHistory}
          onEdit={onEdit}
          onDuplicate={onDuplicate}
          onRetryPermissionCheck={() => detachPromise(stepTypePermissions.retry())}
          permissionCheckError={stepTypePermissions.isError}
          canEdit={canEditVersion}
          canDuplicate={canDuplicateVersion}
          editTooltip={versionEditTooltip}
          duplicateTooltip={versionDuplicateTooltip}
        />
      </div>
    </li>
  )
}
