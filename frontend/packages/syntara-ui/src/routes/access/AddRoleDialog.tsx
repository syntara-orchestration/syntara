import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  SelectList,
  SelectOption,
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Controller, useForm, useWatch, type Control, type FieldErrors, type UseFormRegister } from 'react-hook-form'

import { SynSelect } from '../../components/SynSelect'
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import { addRoleSchema } from './addRoleSchema'
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
  register: UseFormRegister<AddRoleFormData>
  control: Control<AddRoleFormData>
  errors: FieldErrors<AddRoleFormData>
  scope: string
  projectId: string
  projectOptions: { value: string; label: string }[]
  onScopeChange: (scope: string) => void
  onProjectChange: (projectId: string) => void
}

function AddRoleFormFields({
  register,
  control,
  errors,
  scope,
  projectId,
  projectOptions,
  onScopeChange,
  onProjectChange,
}: Readonly<AddRoleFormFieldsProps>) {
  return (
    <>
      <FormGroup label="Name" isRequired fieldId="role-name">
        <TextInput
          id="role-name"
          isRequired
          aria-label="Role name"
          validated={errors.name ? 'error' : 'default'}
          {...register('name')}
        />
        {errors.name ? (
          <FormHelperText>
            <HelperText>
              <HelperTextItem variant="error">{errors.name.message}</HelperTextItem>
            </HelperText>
          </FormHelperText>
        ) : (
          <FormHelperText>
            <HelperText>
              <HelperTextItem>Lowercase alphanumeric with hyphens (e.g. my-custom-role)</HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </FormGroup>

      <FormGroup label="Description" fieldId="role-description">
        <TextInput
          id="role-description"
          aria-label="Role description"
          validated={errors.description ? 'error' : 'default'}
          {...register('description')}
        />
        {errors.description && (
          <FormHelperText>
            <HelperText>
              <HelperTextItem variant="error">{errors.description.message}</HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </FormGroup>

      <FormGroup label="Scope" isRequired fieldId="role-scope" labelHelp={accessControlHelp.scope}>
        <RoleScopeSelect value={scope} onChange={onScopeChange} hasError={!!errors.scope} />
        <FormHelperText>
          <HelperText>
            <HelperTextItem>
              {scope === 'system'
                ? 'System-scoped roles apply across all projects'
                : 'Project-scoped roles are limited to a specific project'}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      </FormGroup>

      {scope === 'project' && (
        <FormGroup label="Project" isRequired fieldId="role-project">
          <TypeaheadSelect
            id="role-project"
            ariaLabel="Project"
            options={projectOptions}
            selected={projectId}
            onChange={onProjectChange}
            placeholder="Select a project..."
            hasError={!!errors.projectId}
          />
          {errors.projectId && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem variant="error">{errors.projectId.message}</HelperTextItem>
              </HelperText>
            </FormHelperText>
          )}
        </FormGroup>
      )}

      <FormGroup label="Policies" isRequired fieldId="role-policies" labelHelp={accessControlHelp.policies}>
        <Controller
          name="policies"
          control={control}
          render={({ field }) => (
            <PolicySelect
              selected={field.value}
              onChange={field.onChange}
              hasError={!!errors.policies}
              scopeProjectId={scope === 'project' ? projectId || null : null}
              projectEligible={scope === 'project'}
              isDisabled={scope === 'project' && !projectId}
            />
          )}
        />
        {scope === 'project' && !projectId ? (
          <FormHelperText>
            <HelperText>
              <HelperTextItem>Select a project first to see available policies</HelperTextItem>
            </HelperText>
          </FormHelperText>
        ) : (
          errors.policies && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem variant="error">{errors.policies.message}</HelperTextItem>
              </HelperText>
            </FormHelperText>
          )
        )}
      </FormGroup>
    </>
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

  const {
    register,
    handleSubmit,
    control,
    setValue,
    setError,
    formState: { errors },
  } = useForm<AddRoleFormData>({
    resolver: zodResolver(addRoleSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: '',
      description: '',
      scope: defaultScope ?? 'system',
      projectId: defaultProjectId ?? '',
      policies: [],
    },
  })

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

  const handleError = useFormMutationErrorHandler<AddRoleFormData>(setError)
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
      onSuccess()
      onClose()
    }
    const onMutationError = handleError({ title: 'Failed to create role' })

    // Project-scoped creates must hit the project roles API so project-admins
    // (role:create:project) succeed — global POST /roles requires system role:create.
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
    <Modal isOpen onClose={onClose} variant="medium">
      <ModalHeader title="Create role" />
      <ModalBody>
        <Form id="add-role-form" onSubmit={handleSubmit(onSubmit)}>
          <AddRoleFormFields
            register={register}
            control={control}
            errors={errors}
            scope={scope}
            projectId={projectId ?? ''}
            projectOptions={projectOptions}
            onScopeChange={handleScopeChange}
            onProjectChange={handleProjectChange}
          />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" form="add-role-form" type="submit" isLoading={isPending} icon={<RhUiAddIcon />}>
          Create role
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
