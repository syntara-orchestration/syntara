import { Fragment } from 'react'

import { FormFieldError } from '../../../../components/FormFieldError'
import { SynForm } from '../../../../components/forms/SynForm'
import { SynFormField } from '../../../../components/forms/SynFormField'
import { SynTextField } from '../../../../components/forms/SynTextField'

import { AuthMethodSelector } from './AuthMethodSelector'
import { credentialHelp } from './credentialFieldHelp'
import type { CredentialFormData } from './credentialFormSchema'
import { CredentialTypeSelect, ProjectSelect } from './CredentialFormSelects'
import { CREDENTIAL_TYPE_HELP } from './CredentialTypeHelp'
import { DynamicFieldRenderer } from './DynamicFieldRenderer'
import type { useCredentialFormModal } from './useCredentialFormModal'

type CredentialFormModalFieldsProps = {
  form: ReturnType<typeof import('../../../../hooks/useSynForm').useSynForm<CredentialFormData>>
  state: ReturnType<typeof useCredentialFormModal>
}

function asStringFieldValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function CredentialFormModalFields({ form, state }: Readonly<CredentialFormModalFieldsProps>) {
  const {
    projects,
    isLoadingProjects,
    projectsError,
    types,
    typesQuery,
    isEditMode,
    isTypeSelectDisabled,
    exclusiveGroups,
    activeGroupIndex,
    handleGroupChange,
    authMethodInsertIndex,
    allExclusiveFieldIds,
    typeInputs,
    visibleFields,
    handleSecretTouch,
    credentialTypeHint,
    handleTypeSelect,
  } = state

  return (
    <SynForm form={form}>
      <SynTextField
        name="name"
        label="Name"
        fieldId="credential-name"
        isRequired
        placeholder="Enter credential name"
        labelHelp={credentialHelp.name}
        ariaLabel="Credential name"
      />
      <SynTextField
        name="description"
        label="Description"
        fieldId="credential-description"
        placeholder="Enter description (optional)"
        labelHelp={credentialHelp.description}
        ariaLabel="Credential description"
      />
      <SynFormField
        name="project_id"
        label="Project"
        fieldId="credential-project"
        isRequired={!isEditMode}
        labelHelp={credentialHelp.project}
      >
        {({ field, fieldState }) => (
          <>
            <ProjectSelect
              value={asStringFieldValue(field.value)}
              onChange={field.onChange}
              onBlur={field.onBlur}
              projects={projects}
              isDisabled={isEditMode || isLoadingProjects}
              isLoading={isLoadingProjects}
              validated={fieldState.error ? 'error' : 'default'}
            />
            {projectsError && <FormFieldError message="Failed to load projects" />}
          </>
        )}
      </SynFormField>
      <SynFormField
        name="credential_type_id"
        label="Credential type"
        fieldId="credential-type"
        isRequired
        labelHelp={CREDENTIAL_TYPE_HELP}
        hint={credentialTypeHint}
      >
        {({ field, fieldState }) => (
          <CredentialTypeSelect
            types={types}
            selectedTypeId={asStringFieldValue(field.value)}
            onSelect={(_event, typeId) => handleTypeSelect(typeId)}
            isDisabled={isTypeSelectDisabled}
            isLoading={typesQuery.isLoading}
            hasError={Boolean(fieldState.error)}
          />
        )}
      </SynFormField>
      {typesQuery.error && <FormFieldError message="Failed to load credential types" />}
      {visibleFields.map((field, index) => {
        const isGroupField = allExclusiveFieldIds.has(field.id)
        const isRequired = isGroupField || (typeInputs?.required.includes(field.id) ?? false)
        return (
          <Fragment key={field.id}>
            {exclusiveGroups.length > 0 && index === authMethodInsertIndex && (
              <AuthMethodSelector
                groups={exclusiveGroups}
                activeIndex={activeGroupIndex}
                onChange={handleGroupChange}
                helpText={typeInputs?.mutually_exclusive_help}
              />
            )}
            <DynamicFieldRenderer
              field={field}
              isRequired={isRequired}
              isEditMode={isEditMode}
              onSecretTouch={handleSecretTouch}
            />
          </Fragment>
        )
      })}
    </SynForm>
  )
}
