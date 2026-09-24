import {
  Button,
  Form,
  MenuToggle,
  type MenuToggleElement,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  SelectList,
  SelectOption,
} from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useWatch } from 'react-hook-form'

import { SynForm } from '../../components/forms/SynForm'
import { SynFormField } from '../../components/forms/SynFormField'
import { SynTextField } from '../../components/forms/SynTextField'
import { SynSelect } from '../../components/SynSelect'
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import type { UseSynFormReturn } from '../../hooks/useSynForm'
import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import { ROLE_NAME_HINT, addRoleSchema } from './addRoleSchema'
import type { AddRoleFormData } from './addRoleSchema'
import { PolicySelect } from './PolicySelect'
import { TypeaheadSelect } from './TypeaheadSelect'
import { useSelectableProjects } from './useAllProjects'

function RoleScopeSelect({
  value,
  onChange,
  hasError,
}: {
  value: string
  onChange: (value: string) => void
  hasError?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <SynSelect
      id="role-scope"
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          status={hasError ? 'danger' : undefined}
          aria-label="Role scope"
        >
          {value === 'system' ? 'System' : 'Project'}
        </MenuToggle>
      )}
    >
      <SelectList>
        <SelectOption value="system">System</SelectOption>
        <SelectOption value="project">Project</SelectOption>
      </SelectList>
    </SynSelect>
  )
}

type AddRoleFormFieldsProps = {
  form: UseSynFormReturn<AddRoleFormData>
  scope: string
  projectId: string
  projectOptions: { value: string; label: string }[]
  onScopeChange: (scope: string) => void
  onProjectChange: (projectId: string) => void
}

function AddRoleFormFields({
  form,
  scope,
  projectId,
  projectOptions,
  onScopeChange,
  onProjectChange,
}: Readonly<AddRoleFormFieldsProps>) {
  const scopeHint =
    scope === 'system'
      ? 'System-scoped roles apply across all projects'
      : 'Project-scoped roles are limited to a specific project'

  return (
    <SynForm form={form}>
      <SynTextField name="name" label="Name" fieldId="role-name" isRequired hint={ROLE_NAME_HINT} />
      <SynTextField name="description" label="Description" fieldId="role-description" />
      <SynFormField<AddRoleFormData, 'scope'>
        name="scope"
        label="Scope"
        fieldId="role-scope"
        isRequired
        labelHelp={accessControlHelp.scope}
        hint={scopeHint}
      >
        {({ field, fieldState }) => (
          <RoleScopeSelect
            value={field.value}
            onChange={(value) => {
              field.onChange(value)
              onScopeChange(value)
            }}
            hasError={!!fieldState.error}
          />
        )}
      </SynFormField>

      {scope === 'project' && (
        <SynFormField<AddRoleFormData, 'projectId'>
          name="projectId"
          label="Project"
          fieldId="role-project"
          isRequired
        >
          {({ field, fieldState }) => (
            <TypeaheadSelect
              id="role-project"
              ariaLabel="Project"
              options={projectOptions}
              selected={projectId}
              onChange={(value) => {
                field.onChange(value)
                onProjectChange(value)
              }}
              placeholder="Select a project..."
              hasError={!!fieldState.error}
            />
          )}
        </SynFormField>
      )}

      <SynFormField<AddRoleFormData, 'policies'>
        name="policies"
        label="Policies"
        fieldId="role-policies"
        isRequired
        labelHelp={accessControlHelp.policies}
        hint={scope === 'project' && !projectId ? 'Select a project first to see available policies' : undefined}
      >
        {({ field, fieldState }) => (
          <PolicySelect
            selected={field.value}
            onChange={field.onChange}
            hasError={!!fieldState.error}
            scopeProjectId={scope === 'project' ? projectId || null : null}
            projectEligible={scope === 'project'}
            isDisabled={scope === 'project' && !projectId}
          />
        )}
      </SynFormField>
    </SynForm>
  )
}

type AddRoleDialogProps = {
  onClose: () => void
  onSuccess: () => void
  defaultScope?: 'system' | 'project'
  defaultProjectId?: string
}

export function AddRoleDialog({ onClose, onSuccess, defaultScope, defaultProjectId }: Readonly<AddRoleDialogProps>) {
  const queryClient = useQueryClient()
  const { showSuccess } = useAlerts()

  const form = useSynForm({
    schema: addRoleSchema,
    defaultValues: {
      name: '',
      description: '',
      scope: defaultScope ?? 'system',
      projectId: defaultProjectId ?? '',
      policies: [],
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose, control, setValue } = form

  const scope = useWatch({ control, name: 'scope' })
  const projectId = useWatch({ control, name: 'projectId' })

  const handleScopeChange = (newScope: string) => {
    setValue('scope', newScope as 'system' | 'project')
    setValue('policies', [])
    if (newScope === 'system') {
      setValue('projectId', '')
    }
  }

  const handleProjectChange = (newProjectId: string) => {
    setValue('projectId', newProjectId)
    setValue('policies', [])
  }

  const { projects: allProjects } = useSelectableProjects()
  const projectOptions = useMemo(
    () =>
      allProjects.filter((p): p is typeof p & { id: string } => !!p.id).map((p) => ({ value: p.id, label: p.name })),
    [allProjects]
  )

  const { mutate: createSystemRole, isPending: isPendingSystem } = accessClient.useMutation('post', '/roles')
  const { mutate: createProjectRole, isPending: isPendingProject } = accessClient.useMutation(
    'post',
    '/projects/{project_id}/roles'
  )
  const isPending = isPendingSystem || isPendingProject

  const onSubmit = (data: AddRoleFormData) => {
    const onMutationSuccess = () => {
      showSuccess({
        title: 'Role created',
        description: (
          <>
            {'The role '}
            {data.name}
            {' has been created successfully.'}
          </>
        ),
      })
      invalidateAuthzCaches(queryClient)
      handleClose()
      onSuccess()
    }
    const onMutationError = handleError({ title: 'Failed to create role' })

    if (data.scope === 'project' && data.projectId) {
      createProjectRole(
        {
          params: { path: { project_id: data.projectId } },
          body: {
            name: data.name,
            description: data.description || undefined,
            policies: data.policies,
          },
        },
        { onSuccess: onMutationSuccess, onError: onMutationError }
      )
      return
    }

    createSystemRole(
      {
        body: {
          name: data.name,
          description: data.description || undefined,
          policies: data.policies,
        },
      },
      { onSuccess: onMutationSuccess, onError: onMutationError }
    )
  }

  return (
    <Modal isOpen onClose={handleClose} variant="medium">
      <ModalHeader title="Create role" />
      <ModalBody>
        <Form id="add-role-form" onSubmit={handleSubmit(onSubmit)}>
          <AddRoleFormFields
            form={form}
            scope={scope}
            projectId={projectId ?? ''}
            projectOptions={projectOptions}
            onScopeChange={handleScopeChange}
            onProjectChange={handleProjectChange}
          />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          form="add-role-form"
          type="submit"
          isDisabled={isPending}
          isLoading={isPending}
          icon={<RhUiAddIcon />}
        >
          Create role
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
