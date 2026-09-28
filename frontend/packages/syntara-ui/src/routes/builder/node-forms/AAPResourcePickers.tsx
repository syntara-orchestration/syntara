import { Button, FormHelperText, HelperText, HelperTextItem, StackItem } from '@patternfly/react-core'
import { useFormContext } from 'react-hook-form'

import { SynFormField } from '../../../components/forms/SynFormField'
import type { useAAPBrowser } from '../../../hooks/useAAPBrowser'
import { isValidAAPTemplateURL } from '../../../utils/urlValidation'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import { AAPTypeaheadSelect } from './AAPTypeaheadSelect'
import { AAPErrorAlert } from './shared/AAPErrorAlert'
import { nodeHelp } from './shared/nodeFieldHelp'

type AAPResourcePickersProps = {
  readonly browser: ReturnType<typeof useAAPBrowser>
}

export function AAPResourcePickers({ browser }: AAPResourcePickersProps) {
  const { setValue, reset, getValues } = useFormContext<AAPJobTemplateFormData>()

  const {
    organizations,
    jobTemplates,
    selectOrganization,
    selectJobTemplate,
    searchOrganizations,
    searchJobTemplates,
    loadingOrgs,
    loadingTemplates,
    error: browserError,
    retryAll,
  } = browser

  const orgOptions = organizations.map((org) => ({ value: org.name, label: org.name }))
  const templateOptions = jobTemplates.map((t) => ({
    value: t.name,
    label: t.name,
    description: t.description ?? undefined,
  }))

  /**
   * Clear all prompt-on-launch field overrides.
   * Called when organization or template changes to reset user-provided values.
   * Uses reset() to batch updates and avoid unnecessary re-renders.
   */
  const clearPromptOverrides = () => {
    const clearedOverrides = {
      inventory_name: '',
      inventory_id: undefined,
      extra_vars: '',
      limit: '',
      tags: '',
      skip_tags: '',
      verbosity: '',
      job_credentials: [],
      job_type: '',
      forks: undefined,
      timeout: undefined,
      job_slice_count: undefined,
      diff_mode: false,
      execution_environment: '',
      execution_environment_id: undefined,
      instance_group: '',
      instance_group_id: undefined,
      labels: [],
    }
    reset({ ...getValues(), ...clearedOverrides }, { keepDirty: false })
  }

  return (
    <>
      <StackItem>
        <SynFormField<AAPJobTemplateFormData, 'organization_name'>
          name="organization_name"
          label="Organization"
          labelHelp={nodeHelp.aapOrganization}
          isRequired
          fieldId="aap-organization"
          hint="AAP organization to browse resources from"
        >
          {({ field, fieldState }) => (
            <AAPTypeaheadSelect
              id="aap-organization"
              ariaLabel="Organization"
              options={orgOptions}
              selected={field.value ?? ''}
              onChange={(value) => {
                field.onChange(value)
                selectOrganization(value)
                setValue('job_template_name', '')
                setValue('job_template_id', undefined)
                clearPromptOverrides()
              }}
              onSearchChange={searchOrganizations}
              placeholder="Select an organization"
              isLoading={loadingOrgs}
              hasError={!!fieldState.error}
            />
          )}
        </SynFormField>
      </StackItem>

      <StackItem>
        <SynFormField<AAPJobTemplateFormData, 'job_template_name'>
          name="job_template_name"
          label="Job template"
          labelHelp={nodeHelp.aapJobTemplate}
          isRequired
          fieldId="aap-jobTemplate"
          hint="AAP job template to launch"
        >
          {({ field, fieldState }) => (
            <AAPTypeaheadSelect
              id="aap-jobTemplate"
              ariaLabel="Job template"
              options={templateOptions}
              selected={field.value ?? ''}
              onChange={(value) => {
                field.onChange(value)
                const selected = jobTemplates.find((t) => t.name === value)
                setValue('job_template_id', selected?.id)
                selectJobTemplate(selected?.id)
                clearPromptOverrides()
              }}
              onSearchChange={searchJobTemplates}
              placeholder="Select a job template"
              isLoading={loadingTemplates}
              hasError={!!fieldState.error}
            />
          )}
        </SynFormField>
        {browser.templateDetail?.url && isValidAAPTemplateURL(browser.templateDetail.url) && (
          <FormHelperText>
            <HelperText>
              <HelperTextItem>
                <Button
                  variant="link"
                  component="a"
                  href={browser.templateDetail.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  isInline
                >
                  View job template in AAP
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
