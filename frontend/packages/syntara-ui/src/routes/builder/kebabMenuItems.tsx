import { DropdownGroup, DropdownItem, DropdownList, Icon } from '@patternfly/react-core'
import {
  RhUiCodeIcon,
  RhUiCheckCircleIcon,
  RhUiExportIcon,
  RhUiClockIcon,
  RhUiHistoryIcon,
  RhUiImportIcon,
  RhUiTrashIcon,
  RhUiMinusCircleFillIcon,
  RhUiDuplicateIcon,
} from '@patternfly/react-icons'
import type { Dispatch } from 'react'

import toolbarStyles from './BuilderEditorToolbar.module.css'
import type { BuilderAction } from './builderReducer'
import type { BuilderPermissions } from './useBuilderPermissions'

export type KebabMenuViewsGroupProps = Readonly<{
  showExistingWorkflowItems: boolean
  handleToggleHistory: () => void
  handleToggleVersionHistory: () => void
  handleToggleDetails: () => void
  closeKebab: () => void
}>

export function KebabMenuViewsGroup({
  showExistingWorkflowItems,
  handleToggleHistory,
  handleToggleVersionHistory,
  handleToggleDetails,
  closeKebab,
}: KebabMenuViewsGroupProps) {
  return (
    <DropdownGroup label="Views">
      <DropdownList>
        {showExistingWorkflowItems && (
          <DropdownItem
            onClick={() => {
              handleToggleHistory()
              closeKebab()
            }}
          >
            <Icon isInline className={toolbarStyles.menuIcon}>
              <RhUiHistoryIcon />
            </Icon>
            Run history
          </DropdownItem>
        )}
        {showExistingWorkflowItems && (
          <DropdownItem
            onClick={() => {
              handleToggleVersionHistory()
              closeKebab()
            }}
          >
            <Icon isInline className={toolbarStyles.menuIcon}>
              <RhUiClockIcon />
            </Icon>
            Version history
          </DropdownItem>
        )}
        <DropdownItem
          onClick={() => {
            handleToggleDetails()
            closeKebab()
          }}
        >
          <Icon isInline className={toolbarStyles.menuIcon}>
            <RhUiCodeIcon />
          </Icon>
          Workflow details
        </DropdownItem>
      </DropdownList>
    </DropdownGroup>
  )
}

export type DuplicateMenuItemProps = Readonly<{
  canDuplicate: boolean
  duplicateTooltip: string
  handleDuplicate: () => void
  closeKebab: () => void
}>

export function DuplicateMenuItem({
  canDuplicate,
  duplicateTooltip,
  handleDuplicate,
  closeKebab,
}: DuplicateMenuItemProps) {
  return (
    <DropdownItem
      isAriaDisabled={!canDuplicate}
      tooltipProps={canDuplicate ? undefined : { content: duplicateTooltip }}
      onClick={
        canDuplicate
          ? () => {
              handleDuplicate()
              closeKebab()
            }
          : undefined
      }
    >
      <Icon isInline className={toolbarStyles.menuIcon}>
        <RhUiDuplicateIcon />
      </Icon>
      Duplicate workflow
    </DropdownItem>
  )
}

export type ImportMenuItemProps = Readonly<{
  canEdit: boolean
  editTooltip: string
  importFileRef: React.RefObject<HTMLInputElement | null>
  closeKebab: () => void
}>

export function ImportMenuItem({ canEdit, editTooltip, importFileRef, closeKebab }: ImportMenuItemProps) {
  return (
    <DropdownItem
      isAriaDisabled={!canEdit}
      tooltipProps={canEdit ? undefined : { content: editTooltip }}
      onClick={
        canEdit
          ? () => {
              importFileRef.current?.click()
              closeKebab()
            }
          : undefined
      }
    >
      <Icon isInline className={toolbarStyles.menuIcon}>
        <RhUiImportIcon />
      </Icon>
      Import workflow
    </DropdownItem>
  )
}

export type UnpublishMenuItemProps = Readonly<{
  canEdit: boolean
  unpublishTooltip: string
  onUnpublish: () => void
  closeKebab: () => void
}>

export function UnpublishMenuItem({ canEdit, unpublishTooltip, onUnpublish, closeKebab }: UnpublishMenuItemProps) {
  return (
    <DropdownItem
      isAriaDisabled={!canEdit}
      tooltipProps={canEdit ? undefined : { content: unpublishTooltip }}
      onClick={
        canEdit
          ? () => {
              onUnpublish()
              closeKebab()
            }
          : undefined
      }
    >
      <Icon isInline className={toolbarStyles.menuIcon}>
        <RhUiMinusCircleFillIcon />
      </Icon>
      Unpublish workflow
    </DropdownItem>
  )
}

export type DeleteMenuItemProps = Readonly<{
  canDelete: boolean
  deleteTooltip: string
  dispatch: Dispatch<BuilderAction>
  closeKebab: () => void
}>

export function DeleteMenuItem({ canDelete, deleteTooltip, dispatch, closeKebab }: DeleteMenuItemProps) {
  return (
    <DropdownItem
      isAriaDisabled={!canDelete}
      tooltipProps={canDelete ? undefined : { content: deleteTooltip }}
      onClick={
        canDelete
          ? () => {
              dispatch({ type: 'SET_DELETE_DIALOG', payload: true })
              closeKebab()
            }
          : undefined
      }
      isDanger={canDelete}
    >
      <Icon isInline className={toolbarStyles.menuIcon}>
        <RhUiTrashIcon />
      </Icon>
      Delete workflow
    </DropdownItem>
  )
}

export type KebabMenuActionsGroupProps = Readonly<{
  showExistingWorkflowItems: boolean
  publishedVersionId: string | null
  canEdit: boolean
  canCreate: boolean
  canDelete: boolean
  tooltips: BuilderPermissions['tooltips']
  handleVerify: (onValid?: () => void) => void
  handleDuplicate: () => void
  handleExport: () => void
  importFileRef: React.RefObject<HTMLInputElement | null>
  onUnpublish: () => void
  dispatch: Dispatch<BuilderAction>
  closeKebab: () => void
}>

export function KebabMenuActionsGroup({
  showExistingWorkflowItems,
  publishedVersionId,
  canEdit,
  canCreate,
  canDelete,
  tooltips,
  handleVerify,
  handleDuplicate,
  handleExport,
  importFileRef,
  onUnpublish,
  dispatch,
  closeKebab,
}: KebabMenuActionsGroupProps) {
  return (
    <DropdownGroup label="Actions">
      <DropdownList>
        <DropdownItem onClick={() => handleVerify()}>
          <Icon isInline className={toolbarStyles.menuIcon}>
            <RhUiCheckCircleIcon />
          </Icon>
          Verify workflow
        </DropdownItem>
        {showExistingWorkflowItems && (
          <DuplicateMenuItem
            canDuplicate={canCreate}
            duplicateTooltip={tooltips.create}
            handleDuplicate={handleDuplicate}
            closeKebab={closeKebab}
          />
        )}
        <DropdownItem onClick={handleExport}>
          <Icon isInline className={toolbarStyles.menuIcon}>
            <RhUiExportIcon />
          </Icon>
          Export workflow
        </DropdownItem>
        <ImportMenuItem
          canEdit={canEdit}
          editTooltip={tooltips.edit}
          importFileRef={importFileRef}
          closeKebab={closeKebab}
        />
        {showExistingWorkflowItems && publishedVersionId != null && (
          <UnpublishMenuItem
            canEdit={canEdit}
            unpublishTooltip={tooltips.unpublish}
            onUnpublish={onUnpublish}
            closeKebab={closeKebab}
          />
        )}
        {showExistingWorkflowItems && (
          <DeleteMenuItem
            canDelete={canDelete}
            deleteTooltip={tooltips.delete}
            dispatch={dispatch}
            closeKebab={closeKebab}
          />
        )}
      </DropdownList>
    </DropdownGroup>
  )
}
