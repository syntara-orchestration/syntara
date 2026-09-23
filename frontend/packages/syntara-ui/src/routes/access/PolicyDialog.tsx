import {
  Button,
  Content,
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
import type { MenuToggleElement } from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Controller, useWatch } from 'react-hook-form'
import type { Control } from 'react-hook-form'
import { z } from 'zod'

import { SynForm } from '../../components/forms/SynForm'
import { SynSelect } from '../../components/SynSelect'
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'
import {
  addProjectPolicySchema,
  policyStatementSchema,
} from '../access-management/projects/addProjectPolicySchema'
import { PolicyFormFields } from '../access-management/projects/PolicyFormFields'

import { accessClient } from './accessClient'
import { TypeaheadSelect } from './TypeaheadSelect'
import type { PolicyRead } from './types'
import { useSelectableProjects } from './useAllProjects'

const policyDialogSchema = addProjectPolicySchema
  .extend({
    scope: z.enum(['system', 'project']),
    projectId: z.string(),
  })
  .superRefine((data, ctx) => {
    if (data.scope === 'project' && !data.projectId) {
      ctx.addIssue({ code: 'custom', path: ['projectId'], message: 'Project is required' })
    }
  })

type PolicyDialogFormData = z.infer<typeof policyDialogSchema>

function PolicyScopeSelect({ value, onChange }: Readonly<{ value: string; onChange: (value: string) => void }>) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <SynSelect
      id="policy-scope"
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, selected) => {
        onChange(String(selected))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((previous) => !previous)}
          isExpanded={isOpen}
          isFullWidth
          aria-label="Policy scope"
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

type ScopeFieldsProps = {
  scope: 'system' | 'project'
  control: Control<PolicyDialogFormData>
  projectOptions: { value: string; label: string }[]
  projectError?: string
  onScopeChange: (scope: 'system' | 'project') => void
}

function PolicyScopeFields(props: Readonly<ScopeFieldsProps>) {
  return (
    <>
      <FormGroup label="Scope" isRequired fieldId="policy-scope">
        <Controller
          name="scope"
          control={props.control}
          render={({ field }) => (
            <PolicyScopeSelect
              value={field.value}
              onChange={(value) => {
                field.onChange(value)
                props.onScopeChange(value as 'system' | 'project')
              }}
            />
          )}
        />
      </FormGroup>
      {props.scope === 'project' && (
        <FormGroup label="Project" isRequired fieldId="policy-project">
          <Controller
            name="projectId"
            control={props.control}
            render={({ field }) => (
              <TypeaheadSelect
                id="policy-project"
                ariaLabel="Project"
                options={props.projectOptions}
                selected={field.value}
                onChange={field.onChange}
                placeholder="Select a project..."
                hasError={!!props.projectError}
              />
            )}
          />
          {props.projectError && <Content component="small">{props.projectError}</Content>}
        </FormGroup>
      )}
    </>
  )
}

type PolicyDialogProps = {
  policy?: PolicyRead
  projectNameMap: Map<string, string>
  onClose: () => void
  onSuccess: () => void
}

export function PolicyDialog({ policy, projectNameMap, onClose, onSuccess }: Readonly<PolicyDialogProps>) {
  const queryClient = useQueryClient()
  const { showSuccess } = useAlerts()
  const mode = policy ? 'edit' : 'create'
  const form = useSynForm<PolicyDialogFormData>({
    schema: policyDialogSchema,
    defaultValues: {
      name: policy?.name ?? '',
      description: policy?.description ?? '',
      statementsJson: policy ? JSON.stringify(policy.statements ?? [], null, 2) : '[]',
      scope: policy?.project_id ? 'project' : 'system',
      projectId: policy?.project_id ?? '',
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose, setValue, control, watch, formState } = form
  const scope = useWatch({ control, name: 'scope' })
  const statementsJson = watch('statementsJson')
  const { projects } = useSelectableProjects()
  const projectOptions = useMemo(
    () => projects.filter((item) => item.id).map((item) => ({ value: item.id ?? '', label: item.name })),
    [projects]
  )
  const { mutate: createPolicy, isPending: isCreating } = accessClient.useMutation('post', '/policies')
  const { mutate: updatePolicy, isPending: isUpdating } = accessClient.useMutation('put', '/policies/{policy_id}')

  const onSubmit = (data: PolicyDialogFormData) => {
    const statements = z.array(policyStatementSchema).parse(JSON.parse(data.statementsJson))
    const onMutationSuccess = () => {
      showSuccess({
        title: mode === 'create' ? 'Policy created' : 'Policy updated',
        description: mode === 'create' ? 'Policy created successfully' : 'Policy updated successfully',
      })
      invalidateAuthzCaches(queryClient)
      onSuccess()
      handleClose()
    }
    const body = { name: data.name, description: data.description || undefined, statements }
    if (policy) {
      updatePolicy(
        { params: { path: { policy_id: policy.id } }, body },
        { onSuccess: onMutationSuccess, onError: handleError({ title: 'Failed to update policy' }) }
      )
      return
    }
    createPolicy(
      { body: { ...body, project_id: data.scope === 'project' ? data.projectId : null } },
      { onSuccess: onMutationSuccess, onError: handleError({ title: 'Failed to create policy' }) }
    )
  }

  const isPending = isCreating || isUpdating
  return (
    <Modal isOpen onClose={handleClose} variant="medium">
      <ModalHeader title={mode === 'create' ? 'Create policy' : 'Edit policy'} />
      <ModalBody>
        <Form id="global-policy-form" onSubmit={handleSubmit(onSubmit)}>
          <SynForm form={form}>
            {policy ? (
              <Content>
                Scope: {policy.project_id ? `Project ${projectNameMap.get(policy.project_id) ?? policy.project_id}` : 'System'}
              </Content>
            ) : (
              <PolicyScopeFields
                scope={scope}
                control={control}
                projectOptions={projectOptions}
                projectError={formState.errors.projectId?.message}
                onScopeChange={(nextScope) => {
                  if (nextScope === 'system') setValue('projectId', '', { shouldValidate: true })
                }}
              />
            )}
            <PolicyFormFields
              statementsJson={statementsJson}
              onAppendStatement={(next) =>
                setValue('statementsJson', next, { shouldDirty: true, shouldValidate: true })
              }
            />
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" form="global-policy-form" type="submit" isLoading={isPending} isDisabled={isPending}>
          {mode === 'create' ? 'Create' : 'Save policy'}
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>Cancel</Button>
      </ModalFooter>
    </Modal>
  )
}
