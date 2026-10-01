import { FormGroup, FormHelperText, HelperText, HelperTextItem, TextInput } from '@patternfly/react-core'
import type { ReactNode } from 'react'
import type { Control, FieldErrors, FieldValues, Path, UseFormRegister } from 'react-hook-form'
import { Controller } from 'react-hook-form'

import { SynFormField } from '../../components/forms/SynFormField'
import { SynTextField } from '../../components/forms/SynTextField'

import { accessControlHelp } from './accessControlFieldHelp'
import { ROLE_NAME_HINT } from './roleFieldHelp'
import type { AddProjectRoleFormData } from '../access-management/projects/addProjectRoleSchema'
import { ProjectPolicySelect } from '../access-management/projects/ProjectPolicySelect'

export type RoleFormFieldIds = {
  name: string
  description: string
  policies: string
}

type RoleFormFieldsProps<T extends FieldValues> = {
  fieldIds: RoleFormFieldIds
  register: UseFormRegister<T>
  control: Control<T>
  errors: FieldErrors<T>
  nameField: Path<T>
  descriptionField: Path<T>
  policiesField: Path<T>
  renderPolicySelect: (props: {
    selected: string[]
    onChange: (value: string[]) => void
    hasError: boolean
  }) => ReactNode
  policiesHelper?: ReactNode
  beforePolicies?: ReactNode
}

export function RoleFormFields<T extends FieldValues>({
  fieldIds,
  register,
  control,
  errors,
  nameField,
  descriptionField,
  policiesField,
  renderPolicySelect,
  policiesHelper,
  beforePolicies,
}: Readonly<RoleFormFieldsProps<T>>) {
  const nameError = errors[nameField]?.message as string | undefined
  const descriptionError = errors[descriptionField]?.message as string | undefined
  const policiesError = errors[policiesField]?.message as string | undefined

  return (
    <>
      <FormGroup label="Name" isRequired fieldId={fieldIds.name}>
        <TextInput
          id={fieldIds.name}
          isRequired
          aria-label="Role name"
          validated={nameError ? 'error' : 'default'}
          {...register(nameField)}
        />
        {nameError ? (
          <FormHelperText>
            <HelperText>
              <HelperTextItem variant="error">{nameError}</HelperTextItem>
            </HelperText>
          </FormHelperText>
        ) : (
          <FormHelperText>
            <HelperText>
              <HelperTextItem>{ROLE_NAME_HINT}</HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </FormGroup>

      <FormGroup label="Description" fieldId={fieldIds.description}>
        <TextInput
          id={fieldIds.description}
          aria-label="Role description"
          validated={descriptionError ? 'error' : 'default'}
          {...register(descriptionField)}
        />
        {descriptionError && (
          <FormHelperText>
            <HelperText>
              <HelperTextItem variant="error">{descriptionError}</HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </FormGroup>

      {beforePolicies}

      <FormGroup label="Policies" isRequired fieldId={fieldIds.policies} labelHelp={accessControlHelp.policies}>
        <Controller
          name={policiesField}
          control={control}
          render={({ field }) =>
            renderPolicySelect({
              selected: field.value as string[],
              onChange: field.onChange,
              hasError: Boolean(policiesError),
            })
          }
        />
        {policiesHelper ??
          (policiesError && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem variant="error">{policiesError}</HelperTextItem>
              </HelperText>
            </FormHelperText>
          ))}
      </FormGroup>
    </>
  )
}

type ProjectRoleSynFormFieldsProps = {
  projectId: string
  fieldIds: RoleFormFieldIds
}

/** Shared name, description, and policies fields for project-scoped role create forms (SynForm). */
export function ProjectRoleSynFormFields({ projectId, fieldIds }: Readonly<ProjectRoleSynFormFieldsProps>) {
  return (
    <>
      <SynTextField name="name" label="Role name" fieldId={fieldIds.name} isRequired hint={ROLE_NAME_HINT} />
      <SynTextField name="description" label="Role description" fieldId={fieldIds.description} />
      <SynFormField<AddProjectRoleFormData, 'policies'>
        name="policies"
        label="Policies"
        fieldId={fieldIds.policies}
        isRequired
        labelHelp={accessControlHelp.policies}
      >
        {({ field, fieldState }) => (
          <ProjectPolicySelect
            projectId={projectId}
            selected={field.value}
            onChange={field.onChange}
            hasError={!!fieldState.error}
          />
        )}
      </SynFormField>
    </>
  )
}
