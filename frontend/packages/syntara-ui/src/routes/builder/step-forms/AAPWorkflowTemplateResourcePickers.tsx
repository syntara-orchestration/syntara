import { Button, FormHelperText, HelperText, HelperTextItem, StackItem } from '@patternfly/react-core'
import { useCallback, useEffect } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { SynFormField } from '../../../components/forms/SynFormField'
import type { useAAPBrowser } from '../../../hooks/useAAPBrowser'
import { isValidAAPTemplateURL } from '../../../utils/urlValidation'

import { getAAPSelectionStaleness } from './aapSelectionStaleness'
import { AAPTypeaheadSelect } from './AAPTypeaheadSelect'
import type { AAPWorkflowTemplateFormData } from './aapWorkflowTemplateSchema'
import { AAPErrorAlert } from './shared/AAPErrorAlert'
import { stepHelp } from './shared/stepFieldHelp'
import { AAP_CREDENTIAL_REQUIRED_HINT } from './shared/stepFieldHelpText'

type AAPWorkflowTemplateResourcePickersProps = {
  readonly browser: ReturnType<typeof useAAPBrowser>
}

export function AAPWorkflowTemplateResourcePickers({ browser }: AAPWorkflowTemplateResourcePickersProps) {
  const { setValue, control } = useFormContext<AAPWorkflowTemplateFormData>()

  const {
    organizations,
    workflowTemplates,
    selectOrganization,
    selectTemplate,
    searchOrganizations,
    searchTemplates,
    loadingOrgs,
    loadingTemplates,
    isActive,
    workflowTemplateDetail,
    error: browserError,
    retryAll,
  } = browser

  const orgOptions = organizations.map((org) => ({ value: org.name, label: org.name }))
  const templateOptions = workflowTemplates.map((template) => ({
    value: template.name,
    label: template.name,
    description:
      'description' in template && typeof template.description === 'string' && template.description.length > 0
        ? template.description
        : undefined,
  }))

  const clearPromptOverrides = useCallback(() => {
    setValue('inventory_name', '')
    setValue('inventory_id', undefined)
    setValue('extra_vars', '')
    setValue('limit', '')
    setValue('scm_branch', '')
    setValue('tags', '')
    setValue('skip_tags', '')
    setValue('labels', [])
  }, [setValue])

  const organizationName = useWatch({ control, name: 'organization_name' })
  const templateName = useWatch({ control, name: 'workflow_job_template_name' })

  // Drop selections the currently loaded lists no longer offer (for example
  // after a credential switch); selections that remain visible are retained
  const staleness = getAAPSelectionStaleness(browser, {
    selectedOrganization: organizationName || undefined,
    selectedTemplateName: templateName || undefined,
  })

  useEffect(() => {
    if (staleness.organization) {
      setValue('organization_name', '')
      setValue('workflow_job_template_name', '')
      setValue('workflow_job_template_id', undefined)
      clearPromptOverrides()
    } else if (staleness.template) {
      setValue('workflow_job_template_name', '')
      setValue('workflow_job_template_id', undefined)
      clearPromptOverrides()
    }
  }, [staleness.organization, staleness.template, setValue, clearPromptOverrides])

  return (
    <>
      <StackItem>
        <SynFormField<AAPWorkflowTemplateFormData, 'organization_name'>
          name="organization_name"
          label="Organization"
          labelHelp={stepHelp.aapOrganization}
          isRequired
          fieldId="aap-wf-organization"
          hint={isActive ? 'AAP organization to browse resources from' : AAP_CREDENTIAL_REQUIRED_HINT}
        >
          {({ field, fieldState }) => (
            <AAPTypeaheadSelect
              id="aap-wf-organization"
              ariaLabel="Organization"
              options={orgOptions}
              selected={field.value ?? ''}
              onChange={(value) => {
                field.onChange(value)
                selectOrganization(value)
                setValue('workflow_job_template_name', '')
                setValue('workflow_job_template_id', undefined)
                clearPromptOverrides()
              }}
              onSearchChange={searchOrganizations}
              placeholder="Select an organization"
              isLoading={loadingOrgs}
              isDisabled={!isActive}
              hasError={!!fieldState.error}
            />
          )}
        </SynFormField>
      </StackItem>

      <StackItem>
        <SynFormField<AAPWorkflowTemplateFormData, 'workflow_job_template_name'>
          name="workflow_job_template_name"
          label="Workflow template"
          labelHelp={stepHelp.aapWorkflowTemplate}
          isRequired
          fieldId="aap-wf-workflowTemplate"
          hint="AAP workflow template to launch"
        >
          {({ field, fieldState }) => (
            <AAPTypeaheadSelect
              id="aap-wf-workflowTemplate"
              ariaLabel="Workflow template"
              options={templateOptions}
              selected={field.value ?? ''}
              onChange={(value) => {
                field.onChange(value)
                const selected = workflowTemplates.find((t) => t.name === value)
                setValue('workflow_job_template_id', selected?.id)
                selectTemplate(selected?.id)
                clearPromptOverrides()
              }}
              onSearchChange={searchTemplates}
              placeholder="Select a workflow template"
              isLoading={loadingTemplates}
              isDisabled={!isActive}
              hasError={!!fieldState.error}
            />
          )}
        </SynFormField>
        {workflowTemplateDetail?.url && isValidAAPTemplateURL(workflowTemplateDetail.url) && (
          <FormHelperText>
            <HelperText>
              <HelperTextItem>
                <Button variant="link" component="a" href={workflowTemplateDetail.url} target="_blank" isInline>
                  View workflow template in AAP
                </Button>
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </StackItem>

      <AAPErrorAlert error={browserError} onRetry={retryAll} />
    </>
  )
}
