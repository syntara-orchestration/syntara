import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  Form,
  FormGroup,
  MenuToggle,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  SelectList,
  SelectOption,
} from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'
import { type Ref, useMemo, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import { FormFieldError, FormFieldWarning } from '../../components/FormFieldError'
import { NxSelect } from '../../components/NxSelect'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useAlerts } from '../../providers/alerts'
import { getErrorMessage, isServiceUnavailableError } from '../../utils/apiErrors'
import { batchedAllSettled } from '../../utils/batchedSettled'
import { detachPromise } from '../../utils/detachPromise'
import { accessClient } from '../access/accessClient'
import { useSelectableProjects } from '../access/useAllProjects'
import { roleAssignmentsQueryKey, useAlreadyAssignedRoles } from '../access/useAlreadyAssignedRoles'

import styles from './AssignRoleModal.module.css'
import { MultiRoleSelect, type RoleOption } from './MultiRoleSelect'
import { buildAssignmentBody, RolePrincipalType } from './RoleAssignmentTypes'

const assignRoleSchema = z.discriminatedUnion('scope', [
  z.object({
    scope: z.literal('system'),
    projectId: z.string().optional(),
    roleIds: z.array(z.string()).min(1, 'Select at least one role'),
  }),
  z.object({
    scope: z.literal('project'),
    projectId: z.string().min(1, 'Project is required'),
    roleIds: z.array(z.string()).min(1, 'Select at least one role'),
  }),
])

type AssignRoleFormData = z.infer<typeof assignRoleSchema>

const ROLE_PAGE_SIZE = 20

type AssignRoleModalProps = {
  principalType: RolePrincipalType
  principalId: string
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

function SingleSelect({
  id,
  ariaLabel,
  value,
  onChange,
  options,
  placeholder,
  hasError,
}: Readonly<{
  id: string
  ariaLabel: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
  hasError?: boolean
}>) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = options.find((o) => o.value === value)?.label ?? placeholder ?? 'Select...'

  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <MenuToggle
      ref={toggleRef}
      onClick={() => setIsOpen(!isOpen)}
      isExpanded={isOpen}
      isFullWidth
      status={hasError ? 'danger' : undefined}
    >
      {selectedLabel}
    </MenuToggle>
  )

  return (
    <NxSelect
      id={id}
      aria-label={ariaLabel}
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      onSelect={(_e, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      selected={value}
      toggle={toggle}
    >
      <SelectList className={styles.rolesList}>
        {options.map((opt) => (
          <SelectOption key={opt.value} value={opt.value} isSelected={opt.value === value}>
            {opt.label}
          </SelectOption>
        ))}
      </SelectList>
    </NxSelect>
  )
}

function showAssignmentResult(
  results: PromiseSettledResult<unknown>[],
  showAlert: ReturnType<typeof useAlerts>['showAlert']
): number {
  const failures = results.filter((r): r is PromiseRejectedResult => r.status === 'rejected')
  const successCount = results.length - failures.length

  if (failures.length === 0) {
    showAlert({
      title: successCount === 1 ? 'Role assigned' : `${String(successCount)} roles assigned`,
      variant: 'success',
      autoDismiss: true,
    })
  } else if (successCount > 0) {
    showAlert({
      title: `${String(successCount)} role(s) assigned, ${String(failures.length)} failed`,
      description: getErrorMessage(failures[0].reason),
      variant: 'warning',
      autoDismiss: true,
    })
  } else {
    const variant = isServiceUnavailableError(failures[0].reason) ? 'warning' : 'danger'
    showAlert({
      title: 'Failed to assign roles',
      description: getErrorMessage(failures[0].reason),
      variant,
      autoDismiss: true,
    })
  }
  return successCount
}

export function AssignRoleModal({
  principalType,
  principalId,
  isOpen,
  onClose,
  onSuccess,
}: Readonly<AssignRoleModalProps>) {
  const queryClient = useQueryClient()
  const { showAlert } = useAlerts()
  const defaultScope = principalType === RolePrincipalType.SERVICE_ACCOUNT ? 'project' : 'system'

  const { control, handleSubmit, setValue, reset } = useForm<AssignRoleFormData>({
    resolver: zodResolver(assignRoleSchema, undefined, { mode: 'sync' }),
    defaultValues: { scope: defaultScope, projectId: '', roleIds: [] },
  })

  const scope = useWatch({ control, name: 'scope' })

  const { projects: allProjects } = useSelectableProjects()

  // ── Server-side role search ──────────────────────────────────────────────
  const [roleSearch, setRoleSearch] = useState('')
  const debouncedRoleSearch = useDebouncedValue(roleSearch)

  const projectId = useWatch({ control, name: 'projectId' })

  const rolesQuery = accessClient.useQuery('get', '/roles', {
    params: {
      query: {
        sort: 'name',
        limit: ROLE_PAGE_SIZE,
        ...(debouncedRoleSearch ? { 'name[contains]': debouncedRoleSearch } : {}),
        scope: scope === 'system' ? 'system' : 'project',
      },
    },
  })

  const {
    assigned: alreadyAssigned,
    isLoading: isAssignmentsLoading,
    isError: isAssignmentsError,
  } = useAlreadyAssignedRoles(principalType, principalId, scope === 'project', projectId ?? '')

  const roleOptions = useMemo((): RoleOption[] => {
    if (isAssignmentsLoading) return []
    const roles = rolesQuery.data?.resources ?? []
    return roles
      .filter((r) => !alreadyAssigned.has(r.name))
      .map((r) => ({ id: r.name, name: r.name, description: r.description ?? null }))
  }, [rolesQuery.data?.resources, alreadyAssigned, isAssignmentsLoading])

  const hasMoreRoles = !!rolesQuery.data?.next
  const isRolesLoading = rolesQuery.isFetching || isAssignmentsLoading

  const projectOptions = useMemo(() => {
    return allProjects
      .filter((p): p is typeof p & { id: string } => !!p.id)
      .map((p) => ({ value: p.id, label: p.name }))
  }, [allProjects])

  const { mutateAsync: createRoleAssignment, isPending: isSystemPending } = accessClient.useMutation(
    'post',
    '/role_assignments'
  )
  const { mutateAsync: createProjectRoleAssignment, isPending: isProjectPending } = accessClient.useMutation(
    'post',
    '/projects/{project_id}/role_assignments'
  )

  const isPending = isSystemPending || isProjectPending

  const handleClose = () => {
    setRoleSearch('')
    reset({ scope: defaultScope, projectId: '', roleIds: [] })
    onClose()
  }

  const onSubmit = handleSubmit(async (data) => {
    const results = await batchedAllSettled(data.roleIds, (roleKey) => {
      const body = buildAssignmentBody(principalType, principalId, roleKey)
      if (data.scope === 'system') {
        return createRoleAssignment({ body })
      }
      return createProjectRoleAssignment({
        params: { path: { project_id: data.projectId } },
        body,
      })
    })
    const successCount = showAssignmentResult(results, showAlert)
    if (successCount > 0) {
      detachPromise(queryClient.invalidateQueries({ queryKey: roleAssignmentsQueryKey(principalType, principalId) }))
      onSuccess()
      handleClose()
    }
  })

  const roleIds = useWatch({ control, name: 'roleIds' })

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium">
      <ModalHeader title="Assign roles" />
      <ModalBody>
        <Form id="assign-role-form" onSubmit={onSubmit}>
          {principalType !== RolePrincipalType.SERVICE_ACCOUNT && (
            <FormGroup label="Scope" fieldId="scope-select" isRequired>
              <Controller
                name="scope"
                control={control}
                render={({ field }) => (
                  <SingleSelect
                    id="scope-select"
                    ariaLabel="Scope"
                    value={field.value}
                    onChange={(value) => {
                      field.onChange(value)
                      setValue('projectId', '', { shouldValidate: true })
                      setValue('roleIds', [], { shouldValidate: true })
                    }}
                    options={[
                      { value: 'system', label: 'System' },
                      { value: 'project', label: 'Project' },
                    ]}
                  />
                )}
              />
            </FormGroup>
          )}
          {scope === 'project' && (
            <FormGroup label="Project" fieldId="project-select" isRequired>
              <Controller
                name="projectId"
                control={control}
                render={({ field, fieldState }) => (
                  <>
                    <SingleSelect
                      id="project-select"
                      ariaLabel="Project"
                      value={field.value ?? ''}
                      onChange={(value) => {
                        field.onChange(value)
                        setValue('roleIds', [], { shouldValidate: true })
                      }}
                      options={projectOptions}
                      placeholder="Select a project..."
                      hasError={!!fieldState.error}
                    />
                    <FormFieldError message={fieldState.error?.message} />
                  </>
                )}
              />
            </FormGroup>
          )}
          <FormGroup label="Roles" fieldId="multi-role-select" isRequired>
            <Controller
              name="roleIds"
              control={control}
              render={({ field, fieldState }) => (
                <>
                  <MultiRoleSelect
                    options={roleOptions}
                    selected={field.value}
                    onChange={field.onChange}
                    onSearchChange={setRoleSearch}
                    hasMore={hasMoreRoles}
                    isLoading={isRolesLoading}
                    hasError={!!fieldState.error}
                  />
                  <FormFieldError message={fieldState.error?.message} />
                  <FormFieldWarning message={isAssignmentsError ? 'Unable to check existing assignments' : undefined} />
                </>
              )}
            />
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" type="submit" form="assign-role-form" isDisabled={isPending} isLoading={isPending}>
          Assign {roleIds.length > 0 ? `(${String(roleIds.length)})` : ''}
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
