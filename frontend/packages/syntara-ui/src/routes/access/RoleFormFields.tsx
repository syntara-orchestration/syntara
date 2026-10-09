import { SynFormField } from '../../components/forms/SynFormField'
import { SynTextField } from '../../components/forms/SynTextField'
import type { AddProjectRoleFormData } from '../access-management/projects/addProjectRoleSchema'
import { ProjectPolicySelect } from '../access-management/projects/ProjectPolicySelect'

import { accessControlHelp } from './accessControlFieldHelp'
import { ROLE_NAME_HINT } from './roleFieldHelp'

export type RoleFormFieldIds = {
  name: string
  description: string
  policies: string
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
