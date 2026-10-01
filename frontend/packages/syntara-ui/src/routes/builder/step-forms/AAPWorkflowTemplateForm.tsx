import { Stack, StackItem, Switch } from '@patternfly/react-core'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo, useRef } from 'react'
import { FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form'

import { SynFormField } from '../../../components/forms/SynFormField'
import { useAAPBrowser } from '../../../hooks/useAAPBrowser'
import { detachPromise } from '../../../utils/detachPromise'
import { AAPIntegrationSection } from '../components/AAPIntegrationSection'
import type { ExpandableCodeEditorHandle } from '../components/ExpandableCodeEditor'
import { StepEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useStepEditorAutoSubmit'
import { hasExpressionValue } from '../utils/aapHelpers'
import { useIsVersionView } from '../VersionViewContext'

import { AAPWorkflowTemplatePromptFields } from './AAPWorkflowTemplatePromptFields'
import { AAPWorkflowTemplateResourcePickers } from './AAPWorkflowTemplateResourcePickers'
import { aapWorkflowTemplateSchema, type AAPWorkflowTemplateFormData } from './aapWorkflowTemplateSchema'
import { WorkflowExpressionTextField } from './ExpressionTextField'
import { ActivityNameField } from './shared/ActivityNameField'
import { zodResolver } from './shared/formSchemaUtils'
import { stepHelp } from './shared/stepFieldHelp'
import { StepFormContainer } from './shared/StepFormContainer'
import stepFormStyles from './shared/stepFormStyles.module.css'
import { StepFormTabsLayout } from './shared/StepFormTabsLayout'
import { StepSettingsForm } from './shared/StepSettingsForm'

export type { AAPWorkflowTemplateFormData } from './aapWorkflowTemplateSchema'

type AAPWorkflowTemplateFormProps = {
  onSubmit: (data: AAPWorkflowTemplateFormData) => void
  onCancel?: () => void
  initialData?: Partial<AAPWorkflowTemplateFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

function AAPFormFields({
  onHeaderContentChange,
  initialData,
  selectedCredentialId,
  selectedIntegrationId,
  projectId,
  extraVarsEditorRef,
}: Readonly<{
  onHeaderContentChange?: (content: ReactNode | null) => void
  initialData?: Partial<AAPWorkflowTemplateFormData>
  selectedCredentialId: string | undefined
  selectedIntegrationId: string | undefined
  projectId?: string
  extraVarsEditorRef: React.RefObject<ExpandableCodeEditorHandle | null>
}>) {
  const isVersionView = useIsVersionView()
  const { register } = useFormContext<AAPWorkflowTemplateFormData>()

  const expressionMode = Boolean(useWatch({ name: 'use_input_variables' }))

  const browser = useAAPBrowser(
    selectedCredentialId,
    {
      organization: initialData?.organization_name,
      templateId: initialData?.workflow_job_template_id,
    },
    'workflow',
    selectedIntegrationId
  )

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="aap-wf-name" ariaLabel="Name" />,
    [register]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const parametersContent = (
    <Stack hasGutter>
      <StackItem>
        <SynFormField<AAPWorkflowTemplateFormData, 'use_input_variables'>
          name="use_input_variables"
          label="Use input variables"
          labelHelp={stepHelp.aapUseExpressions}
          fieldId="aap-wf-expression-mode"
          hideFooter
        >
          {({ field }) => (
            <Switch
              id="aap-wf-expression-mode"
              aria-label="Use input variables"
              isChecked={Boolean(field.value)}
              onChange={(_e, checked) => field.onChange(checked)}
              isDisabled={isVersionView}
            />
          )}
        </SynFormField>
      </StackItem>

      <StackItem>
        <AAPIntegrationSection
          selectedIntegrationId={selectedIntegrationId}
          selectedCredentialId={selectedCredentialId}
          isDisabled={isVersionView}
          projectId={projectId}
        />
      </StackItem>

      <StackItem>
        <fieldset disabled={isVersionView} className={stepFormStyles.disabledFieldset}>
          <Stack hasGutter>
            {expressionMode ? (
              <>
                <StackItem>
                  <WorkflowExpressionTextField
                    name="organization_name"
                    id="aap-wf-organization-expr"
                    label="Organization"
                    placeholder="org name or drag expression"
                    isRequired
                    labelHelp={stepHelp.aapOrganization}
                  />
                </StackItem>
                <StackItem>
                  <WorkflowExpressionTextField
                    name="workflow_job_template_name"
                    id="aap-wf-workflowTemplate-expr"
                    label="Workflow template"
                    placeholder="template name or drag expression"
                    isRequired
                    labelHelp={stepHelp.aapWorkflowTemplate}
                  />
                </StackItem>
                <StackItem>
                  <WorkflowExpressionTextField
                    name="inventory_name"
                    id="aap-wf-inventory-expr"
                    label="Inventory"
                    placeholder="inventory name or drag expression"
                    labelHelp={stepHelp.aapInventory}
                  />
                </StackItem>
                <StackItem>
                  <WorkflowExpressionTextField
                    name="limit"
                    id="aap-wf-limit-expr"
                    label="Limit"
                    placeholder="host pattern or drag expression"
                    labelHelp={stepHelp.aapLimit}
                  />
                </StackItem>
                <StackItem>
                  <WorkflowExpressionTextField
                    name="scm_branch"
                    id="aap-wf-scmBranch-expr"
                    label="Source control branch"
                    placeholder="branch name or drag expression"
                    labelHelp={stepHelp.aapScmBranch}
                  />
                </StackItem>
                <StackItem>
                  <WorkflowExpressionTextField
                    name="tags"
                    id="aap-wf-tags-expr"
                    label="Job tags"
                    placeholder="tags or drag expression"
                    labelHelp={stepHelp.aapWfTags}
                  />
                </StackItem>
                <StackItem>
                  <WorkflowExpressionTextField
                    name="skip_tags"
                    id="aap-wf-skipTags-expr"
                    label="Skip tags"
                    placeholder="skip tags or drag expression"
                    labelHelp={stepHelp.aapWfSkipTags}
                  />
                </StackItem>
                <StackItem>
                  <WorkflowExpressionTextField
                    name="extra_vars"
                    id="aap-wf-extraVars-expr"
                    label="Extra variables"
                    placeholder='{"key": "value"} or drag expression'
                    labelHelp={stepHelp.aapExtraVars}
                  />
                </StackItem>
              </>
            ) : (
              <>
                <AAPWorkflowTemplateResourcePickers browser={browser} />

                <AAPWorkflowTemplatePromptFields
                  templateDetail={browser.workflowTemplateDetail}
                  isLoadingDetail={browser.loadingTemplateDetail}
                  inventories={browser.inventories}
                  loadingInventories={browser.loadingInventories}
                  labels={browser.labels}
                  loadingLabels={browser.loadingLabels}
                  onSearchInventories={browser.searchInventories}
                  onSearchLabels={browser.searchLabels}
                  extraVarsEditorRef={extraVarsEditorRef}
                />
              </>
            )}
          </Stack>
        </fieldset>
      </StackItem>
    </Stack>
  )

  const settingsContent = <StepSettingsForm timeoutStepType="aap" />

  return <StepFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function AAPWorkflowTemplateForm(props: Readonly<AAPWorkflowTemplateFormProps>) {
  const extraVarsEditorRef = useRef<ExpandableCodeEditorHandle>(null)

  const { initialData } = props

  const defaultValues: AAPWorkflowTemplateFormData = {
    name: '',
    credential_id: undefined,
    integration_id: undefined,
    organization_name: '',
    workflow_job_template_name: '',
    workflow_job_template_id: undefined,
    inventory_name: '',
    extra_vars: '',
    limit: '',
    scm_branch: '',
    tags: '',
    skip_tags: '',
    labels: [],
    settings: {},
    ...initialData,
    use_input_variables:
      initialData?.use_input_variables === true ||
      hasExpressionValue(
        initialData?.organization_name,
        initialData?.workflow_job_template_name,
        initialData?.inventory_name,
        initialData?.limit,
        initialData?.scm_branch,
        initialData?.tags,
        initialData?.skip_tags,
        initialData?.extra_vars
      ),
  }

  const methods = useForm<AAPWorkflowTemplateFormData>({
    resolver: zodResolver(aapWorkflowTemplateSchema, undefined, { mode: 'sync' }),
    defaultValues,
    mode: 'onChange',
    reValidateMode: 'onChange',
  })

  const selectedIntegrationId = useWatch({
    control: methods.control,
    name: 'integration_id',
  })

  const selectedCredentialId = useWatch({
    control: methods.control,
    name: 'credential_id',
  })

  const handleSubmit = (data: AAPWorkflowTemplateFormData) => {
    const extra_vars = extraVarsEditorRef.current?.getValue() ?? data.extra_vars ?? ''
    props.onSubmit({ ...data, extra_vars })
  }

  const autoSubmitRef = use(StepEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, handleSubmit)

  const onSubmitWithValidation = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    // Flush extra vars from editor to form state before validation
    const valueFromEditor = extraVarsEditorRef.current?.getValue() ?? methods.getValues('extra_vars') ?? ''
    methods.setValue('extra_vars', valueFromEditor)
    detachPromise(
      methods.trigger().then((valid) => {
        if (valid) {
          return methods.handleSubmit(handleSubmit)()
        }
        // Focus first error field
        const errs = methods.formState.errors
        if (errs.organization_name) methods.setFocus('organization_name')
        else if (errs.workflow_job_template_name) methods.setFocus('workflow_job_template_name')
        else if (errs.extra_vars) extraVarsEditorRef.current?.focus()
      })
    )
  }

  return (
    <FormProvider {...methods}>
      <StepFormContainer formId="aap-workflow-template-form" onSubmit={onSubmitWithValidation}>
        <AAPFormFields
          onHeaderContentChange={props.onHeaderContentChange}
          initialData={props.initialData}
          selectedCredentialId={selectedCredentialId}
          selectedIntegrationId={selectedIntegrationId}
          projectId={props.projectId}
          extraVarsEditorRef={extraVarsEditorRef}
        />
      </StepFormContainer>
    </FormProvider>
  )
}
