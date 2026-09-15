import { Divider, LabelGroup, MenuToggle, SelectList, SelectOption, Spinner } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import type React from 'react'
import { useCallback, useMemo, useState } from 'react'

import { SynLabel } from '../../../components/labels/SynLabel'
import { SynSelect } from '../../../components/SynSelect'
import { useCanI } from '../../../hooks/useCanI'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { detachPromise } from '../../../utils/detachPromise'

import { CreateServiceAccountInlineModal } from './CreateServiceAccountInlineModal'
import { useAllServiceAccounts } from './useAllServiceAccounts'

const CREATE_NEW_VALUE = '__create_new__'

function SASelectToggle({
  id,
  toggleRef,
  label,
  isOpen,
  isDisabled,
  isLoading,
  onToggle,
}: Readonly<{
  id?: string
  toggleRef: React.Ref<HTMLButtonElement>
  label: string
  isOpen: boolean
  isDisabled?: boolean
  isLoading: boolean
  onToggle: () => void
}>) {
  return (
    <MenuToggle id={id} ref={toggleRef} onClick={onToggle} isExpanded={isOpen} isDisabled={isDisabled} isFullWidth>
      {isLoading ? <Spinner size="sm" aria-label="Loading service accounts" /> : label}
    </MenuToggle>
  )
}

type ServiceAccountSelectProps = Readonly<{
  id?: string
  selectedIds: string[]
  onChange: (ids: string[]) => void
  isDisabled?: boolean
}>

export function ServiceAccountSelect({ id, selectedIds, onChange, isDisabled }: ServiceAccountSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const { allowed: canCreate } = useCanI('create', 'service_account')
  const projectId = useWorkflowStore((s) => s.projectId)

  const { serviceAccounts, isLoading, refetch } = useAllServiceAccounts(projectId)

  const selectedSAs = useMemo(
    () => serviceAccounts.filter((sa) => selectedIds.includes(sa.id)),
    [serviceAccounts, selectedIds]
  )

  const toggleLabel = selectedSAs.length > 0 ? `${selectedSAs.length} selected` : 'Select service accounts'

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === CREATE_NEW_VALUE) {
        setIsOpen(false)
        setIsCreateModalOpen(true)
        return
      }
      if (typeof value !== 'string') return
      const updated = selectedIds.includes(value) ? selectedIds.filter((id) => id !== value) : [...selectedIds, value]
      onChange(updated)
    },
    [selectedIds, onChange]
  )

  const handleRemove = useCallback(
    (idToRemove: string) => {
      onChange(selectedIds.filter((id) => id !== idToRemove))
    },
    [selectedIds, onChange]
  )

  const handleCreated = useCallback(
    (saId: string) => {
      detachPromise(refetch())
      if (!selectedIds.includes(saId)) {
        onChange([...selectedIds, saId])
      }
    },
    [selectedIds, onChange, refetch]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<HTMLButtonElement>) => (
      <SASelectToggle
        id={id}
        toggleRef={toggleRef}
        label={toggleLabel}
        isOpen={isOpen}
        isDisabled={isDisabled}
        isLoading={isLoading}
        onToggle={() => setIsOpen((prev) => !prev)}
      />
    ),
    [id, toggleLabel, isOpen, isDisabled, isLoading]
  )

  return (
    <>
      <SynSelect isOpen={isOpen} onOpenChange={setIsOpen} onSelect={handleSelect} toggle={renderToggle}>
        <SelectList>
          {canCreate && (
            <>
              <SelectOption value={CREATE_NEW_VALUE} icon={<RhUiAddIcon />}>
                Create new service account
              </SelectOption>
              <Divider />
            </>
          )}
          {serviceAccounts.map((sa) => (
            <SelectOption
              key={sa.id}
              value={sa.id}
              hasCheckbox
              isSelected={selectedIds.includes(sa.id)}
              description={sa.description ?? undefined}
            >
              {sa.name}
            </SelectOption>
          ))}
          {!isLoading && serviceAccounts.length === 0 && (
            <SelectOption isDisabled value="none">
              No service accounts available
            </SelectOption>
          )}
        </SelectList>
      </SynSelect>

      {selectedSAs.length > 0 && (
        <LabelGroup aria-label="Selected service accounts" style={{ marginTop: 'var(--pf-t--global--spacer--sm)' }}>
          {selectedSAs.map((sa) => (
            <SynLabel key={sa.id} onClose={isDisabled ? undefined : () => handleRemove(sa.id)}>
              {sa.name}
            </SynLabel>
          ))}
        </LabelGroup>
      )}
      <CreateServiceAccountInlineModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreated={handleCreated}
        projectId={projectId ?? undefined}
      />
    </>
  )
}
