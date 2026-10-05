import {
  Button,
  ClipboardCopy,
  Form,
  FormGroup,
  FormHelperText,
  FormSection,
  HelperText,
  HelperTextItem,
  MenuToggle,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  Switch,
  Title,
  Wizard,
  WizardStep,
} from '@patternfly/react-core'
import { useCallback, useState } from 'react'
import { useWatch, type UseFormReturn } from 'react-hook-form'

import { OIDC_REDIRECT_URI } from '../../../../client'
import { FieldHelpPopover } from '../../../../components/FieldHelpPopover'
import { SynForm } from '../../../../components/forms/SynForm'
import { SynFormField } from '../../../../components/forms/SynFormField'
import { SynSwitchField } from '../../../../components/forms/SynSwitchField'
import { SynTextField } from '../../../../components/forms/SynTextField'
import { TagInput } from '../../../../components/forms/TagInput'
import { ProviderIcon } from '../../../../components/ProviderIcon'
import { SynSelect } from '../../../../components/SynSelect'
import { detachPromise } from '../../../../utils/detachPromise'

import { UserClaimMappingFields } from './ClaimMappingFields'
import { ConnectionFields } from './ConnectionFields'
import styles from './IdentityProviderFormFields.module.css'
import { type IdentityProviderFormData } from './identityProviderFormSchema'
import { idpHelp } from './idpFieldHelp'
import { IdpTypeKey, IDP_TYPE_OPTIONS, IDP_TYPE_PRESETS } from './idpTypePresets'
import { JmespathExpressionField } from './JmespathExpressionField'
import { WizardNavFooter } from './WizardNavFooter'

function getScopesHelperText(hasError: unknown, isPresetTemplate: boolean): string | undefined {
  if (hasError) return undefined
  if (isPresetTemplate) return 'Pre-configured by provider template. Select Custom to modify.'
  return 'Type a scope and press Enter or comma to add'
}

type IdpTypeSelectDeps = Readonly<{
  onTypeChange: (value: string) => void
  onBlur: () => void
  setIsOpen: (open: boolean) => void
}>

function idpTypeOnSelect(deps: IdpTypeSelectDeps, _event: unknown, value: unknown): void {
  const val = String(value)
  deps.onTypeChange(val)
  deps.onBlur()
  deps.setIsOpen(false)
}

function toggleIdpTypeMenuExpanded(setIsOpen: React.Dispatch<React.SetStateAction<boolean>>): void {
  setIsOpen((prev) => !prev)
}

type IdpTypeMenuToggleProps = Readonly<{
  toggleRef: React.Ref<HTMLButtonElement>
  isOpen: boolean
  setIsOpen: React.Dispatch<React.SetStateAction<boolean>>
  fieldValue: string | undefined
  selectedLabel: string | undefined
  hasError: boolean
}>

function IdpTypeMenuToggle({
  toggleRef,
  isOpen,
  setIsOpen,
  fieldValue,
  selectedLabel,
  hasError,
}: IdpTypeMenuToggleProps) {
  function handleToggleClick(): void {
    toggleIdpTypeMenuExpanded(setIsOpen)
  }

  return (
    <MenuToggle
      ref={toggleRef}
      onClick={handleToggleClick}
      isExpanded={isOpen}
      isFullWidth
      status={hasError ? 'danger' : undefined}
    >
      {fieldValue ? (
        <>
          <ProviderIcon
            name={selectedLabel ?? ''}
            idpType={fieldValue}
            style={{ marginRight: 'var(--pf-t--global--spacer--sm)' }}
          />
          {selectedLabel}
        </>
      ) : (
        'Select a provider template...'
      )}
    </MenuToggle>
  )
}

function IdpTypeField({ onTypeChange }: Readonly<{ onTypeChange: (value: string) => void }>) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <SynFormField<IdentityProviderFormData, 'idpType'>
      name="idpType"
      label="Provider template"
      fieldId="idp-type"
      isRequired
      labelHelp={idpHelp.providerTemplate}
    >
      {({ field, fieldState }) => {
        const selectedLabel = IDP_TYPE_OPTIONS.find((o) => o.value === field.value)?.label
        const selectDeps: IdpTypeSelectDeps = {
          onTypeChange,
          onBlur: field.onBlur,
          setIsOpen,
        }

        return (
          <SynSelect
            id="idp-type"
            isOpen={isOpen}
            selected={field.value || undefined}
            onSelect={(event, value) => idpTypeOnSelect(selectDeps, event, value)}
            onOpenChange={setIsOpen}
            toggle={(toggleRef) => (
              <IdpTypeMenuToggle
                toggleRef={toggleRef}
                isOpen={isOpen}
                setIsOpen={setIsOpen}
                fieldValue={field.value}
                selectedLabel={selectedLabel}
                hasError={Boolean(fieldState.error)}
              />
            )}
          >
            <SelectList>
              {IDP_TYPE_OPTIONS.map((opt) => (
                <SelectOption key={opt.value} value={opt.value} isSelected={field.value === opt.value}>
                  <ProviderIcon
                    name={opt.label}
                    idpType={opt.value}
                    style={{ marginRight: 'var(--pf-t--global--spacer--sm)' }}
                  />
                  {opt.label}
                </SelectOption>
              ))}
            </SelectList>
          </SynSelect>
        )
      }}
    </SynFormField>
  )
}

function ScopesField({ isPresetTemplate }: Readonly<{ isPresetTemplate: boolean }>) {
  return (
    <SynFormField<IdentityProviderFormData, 'scopes'>
      name="scopes"
      label="Scopes"
      fieldId="scopes"
      isRequired
      labelHelp={
        <FieldHelpPopover helpText="OAuth 2.0 scopes to request from the identity provider during authentication." />
      }
      hideFooter
    >
      {({ field, fieldState }) => {
        const scopesList = field.value ? field.value.split(/\s+/).filter(Boolean) : []
        return (
          <TagInput
            id="scopes"
            value={scopesList}
            onChange={(arr) => field.onChange(arr.join(' '))}
            ariaLabel="Add scope"
            placeholder="openid"
            isDisabled={isPresetTemplate}
            helperText={getScopesHelperText(fieldState.error, isPresetTemplate)}
          />
        )
      }}
    </SynFormField>
  )
}

function AllowAllAuthenticatedField() {
  return (
    <SynFormField<IdentityProviderFormData, 'allowAllAuthenticated'>
      name="allowAllAuthenticated"
      label="Allow all authenticated"
      fieldId="allow-all-authenticated"
      hideFormGroupLabel
      hideFooter
    >
      {({ field }) => (
        <>
          <Switch
            id="allow-all-authenticated"
            label="Allow all authenticated"
            hasCheckIcon
            isChecked={field.value}
            onChange={(_event, checked) => field.onChange(checked)}
          />
          <FormHelperText>
            <HelperText>
              <HelperTextItem>
                Allow all users from this identity provider to log in, even without group mapping matches.
              </HelperTextItem>
              {field.value && (
                <HelperTextItem variant="warning">
                  Any user who authenticates via this provider will be granted access. Only enable this if you trust all
                  users from this identity provider.
                </HelperTextItem>
              )}
            </HelperText>
          </FormHelperText>
        </>
      )}
    </SynFormField>
  )
}

export type TestResultData = {
  claimsSupported?: string[] | null
  claimAliases?: Record<string, string[]> | null
}

type IdentityProviderFormFieldsProps = {
  form: UseFormReturn<IdentityProviderFormData>
  isEdit?: boolean
  testResult?: TestResultData | null
  onTestConnection?: () => Promise<void>
  isTesting?: boolean
  submitLabel?: string
  isSaving?: boolean
  onSubmit?: (goToStepById: (id: string) => void) => void
  onCancel?: () => void
}

export function IdentityProviderFormFields({
  form,
  isEdit,
  testResult,
  onTestConnection,
  isTesting,
  submitLabel,
  isSaving,
  onSubmit,
  onCancel,
}: Readonly<IdentityProviderFormFieldsProps>) {
  const { control, setValue, trigger } = form
  const claimsSupported = testResult?.claimsSupported
  const claimAliases = testResult?.claimAliases
  const autoDiscovery = useWatch({ control, name: 'autoDiscovery' })
  const idpType = useWatch({ control, name: 'idpType' })
  const isPresetTemplate = Boolean(idpType && idpType !== IdpTypeKey.CUSTOM)

  const handleIdpTypeChange = useCallback(
    (value: string) => {
      setValue('idpType', value, { shouldValidate: true })
      const preset = IDP_TYPE_PRESETS[value]
      if (!preset) return
      setValue('scopes', preset.scopes)
      setValue('claimMapping', preset.claimMapping)
      setValue('groupMapping', { jmespathExpression: preset.groupMappingExpression, entries: [] })
      setValue('aapRoleMappingEnabled', preset.aapRoleMappingEnabled)
      setValue('enableRpInitiatedLogout', preset.enableRpInitiatedLogout)
    },
    [setValue]
  )

  return (
    <SynForm form={form}>
      <Wizard
        isVisitRequired={false}
        footer={
          <WizardNavFooter
            trigger={trigger}
            submitLabel={submitLabel}
            isSaving={isSaving}
            onSubmit={onSubmit}
            onCancel={onCancel}
          />
        }
      >
        <WizardStep name="Provider configuration" id="provider-config">
          <Stack hasGutter>
            <StackItem>
              <Title headingLevel="h2" size="lg">
                Provider configuration
              </Title>
            </StackItem>
            <StackItem>
              <Form className={styles.formMaxWidth}>
                <FormSection title="General" titleElement="h3">
                  <IdpTypeField onTypeChange={handleIdpTypeChange} />

                  <SynTextField
                    name="name"
                    label="Provider name"
                    fieldId="provider-name"
                    isRequired
                    placeholder="Enter provider name"
                    labelHelp={<FieldHelpPopover helpText="A unique display name for this identity provider." />}
                  />

                  <SynFormField<IdentityProviderFormData, 'enabled'>
                    name="enabled"
                    label="Enable provider"
                    fieldId="provider-enabled"
                  >
                    {({ field }) => (
                      <Switch
                        id="provider-enabled"
                        label="Enabled"
                        hasCheckIcon
                        isChecked={field.value}
                        onChange={(_event, checked) => field.onChange(checked)}
                      />
                    )}
                  </SynFormField>
                </FormSection>

                <FormSection title="Connection" titleElement="h3">
                  <ConnectionFields autoDiscovery={autoDiscovery} isEdit={isEdit} />

                  {onTestConnection && (
                    <FormGroup fieldId="test-connection">
                      <Button
                        variant="secondary"
                        onClick={() => detachPromise(onTestConnection())}
                        isLoading={isTesting}
                        isDisabled={isTesting}
                      >
                        Test connection
                      </Button>
                    </FormGroup>
                  )}
                </FormSection>

                <FormSection title="Options" titleElement="h3">
                  <FormGroup
                    label="Redirect URI"
                    fieldId="redirect-uri"
                    labelHelp={
                      <FieldHelpPopover helpText="Copy this value into your identity provider's OAuth app configuration as the allowed redirect URI." />
                    }
                  >
                    <ClipboardCopy isReadOnly>{OIDC_REDIRECT_URI}</ClipboardCopy>
                  </FormGroup>

                  <ScopesField isPresetTemplate={isPresetTemplate} />
                  <AllowAllAuthenticatedField />
                  {idpType === IdpTypeKey.AAP && (
                    <SynSwitchField
                      name="aapRoleMappingEnabled"
                      label="Map AAP system roles to groups"
                      fieldId="aap-role-mapping-enabled"
                      hint="Map AAP system roles (administrator, auditor, user) to built-in admins, auditors, and users groups."
                    />
                  )}
                  <SynSwitchField
                    name="enableRpInitiatedLogout"
                    label="Single logout"
                    fieldId="enable-rp-initiated-logout"
                    hint="When enabled, users will be redirected to the identity provider's logout page on sign-out."
                  />
                </FormSection>
              </Form>
            </StackItem>
          </Stack>
        </WizardStep>

        <WizardStep name="Claim mapping" id="claim-mapping">
          <Stack hasGutter>
            <StackItem>
              <Title headingLevel="h2" size="lg">
                Claim mapping
              </Title>
            </StackItem>
            <StackItem>
              <Form className={styles.formMaxWidth}>
                <UserClaimMappingFields
                  claimsSupported={claimsSupported}
                  claimAliases={claimAliases}
                  isReadOnly={isPresetTemplate}
                />
                <JmespathExpressionField idpType={idpType} />
              </Form>
            </StackItem>
          </Stack>
        </WizardStep>
      </Wizard>
    </SynForm>
  )
}
