import { Alert, AlertActionCloseButton, Stack, StackItem } from '@patternfly/react-core'
import { useWatch, type Control } from 'react-hook-form'

import { GroupFormModal } from '../../GroupFormModal'

import { AdvancedSection, GroupMappingFormActions, MappingTable } from './GroupMappingComponents'
import type { GroupMappingEditFormValues } from './groupMappingEditFormSchema'
import { signInAlertTitle } from './groupMappingFormUtils'
import type { MappedGroup } from './groupMappingUtils'

export type GroupMappingEditPanelProps = {
  signInAlert: { variant: 'success' | 'warning' | 'danger'; message: string } | null
  onDismissSignInAlert: () => void
  control: Control<GroupMappingEditFormValues>
  mappingRows: { rowId: string; index: number }[]
  mappedGroups: MappedGroup[]
  onRemove: (index: number) => void
  onAdd: () => void
  onCreateGroup: (index: number) => void
  onReDiscover: () => void
  isListening: boolean
  defaultExpression: string | null
  idpType?: string | null
  rawClaims: string | null
  createGroupForIndex: number | null
  onCloseCreateGroup: () => void
  onGroupCreated: () => void
}

function GroupMappingCreateGroupModal({
  index,
  onClose,
  onSuccess,
  control,
}: Readonly<{
  index: number
  onClose: () => void
  onSuccess: () => void
  control: Control<GroupMappingEditFormValues>
}>) {
  const idpGroupValue = useWatch({ control, name: `entries.${index}.idpGroupValue` })

  return <GroupFormModal isOpen initialName={idpGroupValue} onClose={onClose} onSuccess={onSuccess} />
}

export function GroupMappingEditPanel({
  signInAlert,
  onDismissSignInAlert,
  control,
  mappingRows,
  mappedGroups,
  onRemove,
  onAdd,
  onCreateGroup,
  onReDiscover,
  isListening,
  defaultExpression,
  idpType,
  rawClaims,
  createGroupForIndex,
  onCloseCreateGroup,
  onGroupCreated,
}: Readonly<GroupMappingEditPanelProps>) {
  return (
    <Stack hasGutter>
      {signInAlert && (
        <StackItem>
          <Alert
            variant={signInAlert.variant}
            title={signInAlertTitle(signInAlert.variant)}
            isInline
            actionClose={<AlertActionCloseButton onClose={onDismissSignInAlert} />}
          >
            {signInAlert.message}
          </Alert>
        </StackItem>
      )}
      <MappingTable
        rows={mappingRows}
        control={control}
        mappedGroups={mappedGroups}
        onRemove={onRemove}
        onAdd={onAdd}
        onCreateGroup={onCreateGroup}
        showAddMappingAction={false}
      />
      <StackItem>
        <GroupMappingFormActions onAdd={onAdd} onReDiscover={onReDiscover} isListening={isListening} />
      </StackItem>
      <StackItem>
        <AdvancedSection
          control={control}
          defaultExpression={defaultExpression}
          idpType={idpType}
          rawClaims={rawClaims}
        />
      </StackItem>
      {createGroupForIndex !== null && (
        <GroupMappingCreateGroupModal
          index={createGroupForIndex}
          control={control}
          onClose={onCloseCreateGroup}
          onSuccess={onGroupCreated}
        />
      )}
    </Stack>
  )
}
