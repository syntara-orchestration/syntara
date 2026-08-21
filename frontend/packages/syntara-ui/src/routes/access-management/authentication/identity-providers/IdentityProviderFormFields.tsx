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
  TextInput,
  Title,
  Wizard,
  WizardStep,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import { useCallback, useState } from 'react'
import { Controller, useWatch, type Control, type UseFormSetValue, type UseFormTrigger } from 'react-hook-form'

import { OIDC_REDIRECT_URI } from '../../../../client'
import { TagInput } from '../../../../components/forms/TagInput'
import { ProviderIcon } from '../../../../components/ProviderIcon'
import { SynSelect } from '../../../../components/SynSelect'
import { detachPromise } from '../../../../utils/detachPromise'

import { UserClaimMappingFields } from './ClaimMappingFields'
import { ConnectionFields } from './ConnectionFields'
import { FieldErrorMessage, FieldHelpPopover } from './formFieldHelpers'
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

function IdpTypeField({
  control,
  onTypeChange,
}: Readonly<{ control: Control<IdentityProviderFormData>; onTypeChange: (value: string) => void }>) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Controller
      name="idpType"
      control={control}
      render={({ field, fieldState }) => {
        const selectedLabel = IDP_TYPE_OPTIONS.find((o) => o.value === field.value)?.label
        const selectDeps: IdpTypeSelectDeps = {
          onTypeChange,
          onBlur: field.onBlur,
          setIsOpen,
        }

        return (
          <FormGroup label="Provider template" fieldId="idp-type" isRequired labelHelp={idpHelp.providerTemplate}>
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

            <FieldErrorMessage error={fieldState.error} />
          </FormGroup>
        )
      }}
    />
  )
}

function RpInitiatedLogoutField({ control }: Readonly<{ control: Control<IdentityProviderFormData> }>) {
  return (
    <Controller
      name="enableRpInitiatedLogout"
      control={control}
      render={({ field }) => (
        <FormGroup fieldId="enable-rp-initiated-logout">
          <Switch
            id="enable-rp-initiated-logout"
            label="Single logout"
            hasCheckIcon
            isChecked={field.value}
            onChange={(_event, checked) => field.onChange(checked)}
          />
          <FormHelperText>
            <HelperText>
              <HelperTextItem>
                When enabled, users will be redirected to the identity provider&apos;s logout page on sign-out.
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        </FormGroup>
      )}
    />
  )
}

function ScopesField({
  control,
  isPresetTemplate,
}: Readonly<{ control: Control<IdentityProviderFormData>; isPresetTemplate: boolean }>) {
  return (
    <Controller
      name="scopes"
      control={control}
      render={({ field, fieldState }) => {
        const scopesList = field.value ? field.value.split(/\s+/).filter(Boolean) : []
        return (
          <FormGroup
            label="Scopes"
            fieldId="scopes"
            isRequired
            labelHelp={
              <FieldHelpPopover helpText="OAuth 2.0 scopes to request from the identity provider during authentication." />
            }
          >
            <TagInput
              id="scopes"
              value={scopesList}
              onChange={(arr) => field.onChange(arr.join(' '))}
              ariaLabel="Add scope"
              placeholder="openid"
              isDisabled={isPresetTemplate}
              helperText={getScopesHelperText(fieldState.error, isPresetTemplate)}
            />
            {fieldState.error && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                    {fieldState.error.message}
                  </HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>
        )
      }}
    />
  )
}

function AllowAllAuthenticatedField({ control }: Readonly<{ control: Control<IdentityProviderFormData> }>) {
  return (
    <Controller
      name="allowAllAuthenticated"
      control={control}
      render={({ field }) => (
        <FormGroup fieldId="allow-all-authenticated">
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
        </FormGroup>
      )}
    />
  )
}

function AapRoleMappingField({ control }: Readonly<{ control: Control<IdentityProviderFormData> }>) {
  return (
    <Controller
      name="aapRoleMappingEnabled"
      control={control}
      render={({ field }) => (
        <FormGroup fieldId="aap-role-mapping-enabled">
          <Switch
            id="aap-role-mapping-enabled"
            label="Map AAP system roles to groups"
            hasCheckIcon
            isChecked={field.value}
            onChange={(_event, checked) => field.onChange(checked)}
          />
          <FormHelperText>
            <HelperText>
              <HelperTextItem>
                Map AAP system roles (administrator, auditor, user) to built-in admins, auditors, and users groups.
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        </FormGroup>
      )}
    />
  )
}

export type TestResultData = {
  claimsSupported?: string[] | null
  claimAliases?: Record<string, string[]> | null
}

type IdentityProviderFormFieldsProps = {
  control: Control<IdentityProviderFormData>
  setValue: UseFormSetValue<IdentityProviderFormData>
  trigger: UseFormTrigger<IdentityProviderFormData>
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
  control,
  setValue,
  trigger,
  isEdit,
  testResult,
  onTestConnection,
  isTesting,
  submitLabel,
  isSaving,
  onSubmit,
  onCancel,
}: Readonly<IdentityProviderFormFieldsProps>) {
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
                <IdpTypeField control={control} onTypeChange={handleIdpTypeChange} />

                <Controller
                  name="name"
                  control={control}
                  render={({ field, fieldState }) => (
                    <FormGroup
                      label="Provider name"
                      fieldId="provider-name"
                      isRequired
                      labelHelp={<FieldHelpPopover helpText="A unique display name for this identity provider." />}
                    >
                      <TextInput
                        id="provider-name"
                        placeholder="Enter provider name"
                        validated={fieldState.error ? 'error' : 'default'}
                        {...field}
                      />
                      <FieldErrorMessage error={fieldState.error} />
                    </FormGroup>
                  )}
                />

                <Controller
                  name="enabled"
                  control={control}
                  render={({ field }) => (
                    <FormGroup label="Enable provider" fieldId="provider-enabled">
                      <Switch
                        id="provider-enabled"
                        label="Enabled"
                        hasCheckIcon
                        isChecked={field.value}
                        onChange={(_event, checked) => field.onChange(checked)}
                      />
                    </FormGroup>
                  )}
                />
              </FormSection>

              <FormSection title="Connection" titleElement="h3">
                <ConnectionFields control={control} autoDiscovery={autoDiscovery} isEdit={isEdit} />

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

                <ScopesField control={control} isPresetTemplate={isPresetTemplate} />
                <AllowAllAuthenticatedField control={control} />
                {idpType === IdpTypeKey.AAP && <AapRoleMappingField control={control} />}
                <RpInitiatedLogoutField control={control} />
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
                control={control}
                claimsSupported={claimsSupported}
                claimAliases={claimAliases}
                isReadOnly={isPresetTemplate}
              />
              <JmespathExpressionField control={control} idpType={idpType} />
            </Form>
          </StackItem>
        </Stack>
      </WizardStep>
    </Wizard>
  )
}
