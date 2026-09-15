import {
  Checkbox,
  Content,
  ContentVariants,
  ExpandableSection,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  TextArea,
  TextInput,
  Title,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { type ReactElement, type ReactNode, type Ref, useCallback, useState } from 'react'
import { Controller, useWatch, type Control, type UseFormSetValue } from 'react-hook-form'

import { SynSelect } from '../../../../components/SynSelect'
import { integrationHelp } from '../integrationFieldHelp'
import { PROVIDERS_HIDING_BASE_URL, PROVIDERS_REQUIRING_BASE_URL } from '../integrationFilters'

import { INTEGRATION_TYPE_OPTIONS, PROVIDER_HINT_OPTIONS, type IntegrationFormData } from './integrationFormSchema'
import { ScopeFields } from './ScopeFields'
import styles from './WizardSteps.module.css'

type ControlledTextFieldProps = Readonly<{
  control: Control<IntegrationFormData>
  name: 'name' | 'description' | 'configuration.base_url'
  label: string
  fieldId: string
  placeholder: string
  isRequired?: boolean
  labelHelp?: ReactElement
}>

function ControlledTextField({
  control,
  name,
  label,
  fieldId,
  placeholder,
  isRequired,
  labelHelp,
}: ControlledTextFieldProps) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <FormGroup label={label} fieldId={fieldId} isRequired={isRequired} labelHelp={labelHelp}>
          <TextInput
            id={fieldId}
            placeholder={placeholder}
            aria-required={isRequired || undefined}
            validated={fieldState.error ? 'error' : 'default'}
            value={field.value ?? ''}
            onChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
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
      )}
    />
  )
}

function IntegrationTypeMenuToggle({
  toggleRef,
  value,
  onClick,
  isExpanded,
}: Readonly<{
  toggleRef: Ref<MenuToggleElement>
  value: string
  onClick: () => void
  isExpanded: boolean
}>) {
  const label = INTEGRATION_TYPE_OPTIONS.find((opt) => opt.value === value)?.label ?? value
  return (
    <MenuToggle ref={toggleRef} onClick={onClick} isExpanded={isExpanded} isFullWidth>
      {label}
    </MenuToggle>
  )
}

function ProviderHintMenuToggle({
  toggleRef,
  value,
  onClick,
  isExpanded,
}: Readonly<{
  toggleRef: Ref<MenuToggleElement>
  value: string
  onClick: () => void
  isExpanded: boolean
}>) {
  const label = PROVIDER_HINT_OPTIONS.find((opt) => opt.value === value)?.label ?? value
  return (
    <MenuToggle ref={toggleRef} onClick={onClick} isExpanded={isExpanded} isFullWidth>
      {label}
    </MenuToggle>
  )
}

function IntegrationTypeSelect({
  value,
  isOpen,
  onOpenChange,
  onSelect,
  renderToggle,
}: Readonly<{
  value: string
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (value: string) => void
  renderToggle: (toggleRef: Ref<MenuToggleElement>) => ReactNode
}>) {
  return (
    <SynSelect
      id="integration-type"
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, v) => {
        if (typeof v === 'string') onSelect(v)
      }}
      onOpenChange={onOpenChange}
      toggle={renderToggle}
      shouldFocusToggleOnSelect
    >
      <SelectList>
        {INTEGRATION_TYPE_OPTIONS.map((opt) => (
          <SelectOption key={opt.value} value={opt.value}>
            {opt.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

function ProviderHintSelect({
  value,
  isOpen,
  onOpenChange,
  onSelect,
  renderToggle,
}: Readonly<{
  value: string | undefined
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (value: string) => void
  renderToggle: (toggleRef: Ref<MenuToggleElement>) => ReactNode
}>) {
  return (
    <SynSelect
      id="provider-hint"
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, v) => {
        if (typeof v === 'string') onSelect(v)
      }}
      onOpenChange={onOpenChange}
      toggle={renderToggle}
      shouldFocusToggleOnSelect
    >
      <SelectList>
        {PROVIDER_HINT_OPTIONS.map((opt) => (
          <SelectOption key={opt.value} value={opt.value}>
            {opt.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

function SecurityFields({ control }: Readonly<{ control: Control<IntegrationFormData> }>) {
  const [isExpanded, setIsExpanded] = useState(false)
  const skipTlsVerify = useWatch({ control, name: 'configuration.insecure_skip_tls_verify' })

  return (
    <ExpandableSection
      toggleText="Security"
      isExpanded={isExpanded}
      onToggle={(_e, expanded) => setIsExpanded(expanded)}
      isIndented
    >
      <div className={styles.securityFields}>
        <Controller
          name="configuration.allow_http"
          control={control}
          render={({ field }) => (
            <Checkbox
              id="allow-http"
              label="Allow HTTP connections"
              description="Permits unencrypted HTTP URLs for this integration"
              isChecked={field.value}
              onChange={(_event, checked) => field.onChange(checked)}
            />
          )}
        />
        <Controller
          name="configuration.insecure_skip_tls_verify"
          control={control}
          render={({ field }) => (
            <Checkbox
              id="insecure-skip-tls-verify"
              label="Disable TLS certificate verification"
              description="Skips validation of the server's TLS certificate on connections"
              isChecked={field.value}
              onChange={(_event, checked) => field.onChange(checked)}
              body={
                skipTlsVerify ? (
                  <HelperText>
                    <HelperTextItem variant="warning">
                      The server's TLS certificate will not be verified. Only enable in trusted networks.
                    </HelperTextItem>
                  </HelperText>
                ) : undefined
              }
            />
          )}
        />
        {!skipTlsVerify && (
          <FormGroup label="CA certificate" fieldId="ca-certificate">
            <Controller
              name="configuration.ca_certificate"
              control={control}
              render={({ field }) => (
                <TextArea
                  id="ca-certificate"
                  placeholder={'-----BEGIN CERTIFICATE-----\n\n-----END CERTIFICATE-----'}
                  aria-label="CA certificate"
                  resizeOrientation="vertical"
                  rows={4}
                  value={field.value ?? ''}
                  onChange={(_event, value) => field.onChange(value || null)}
                  onBlur={field.onBlur}
                  name={field.name}
                />
              )}
            />
            <FormHelperText>
              <HelperText>
                <HelperTextItem>
                  PEM-encoded CA certificate to trust for this integration's TLS connections.
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          </FormGroup>
        )}
      </div>
    </ExpandableSection>
  )
}

type IntegrationDetailsStepProps = Readonly<{
  control: Control<IntegrationFormData>
  setValue: UseFormSetValue<IntegrationFormData>
  onTypeChange: (newType: string) => void
}>

export function IntegrationDetailsStep({ control, setValue, onTypeChange }: IntegrationDetailsStepProps) {
  const scope = useWatch({ control, name: 'scope' })
  const integrationType = useWatch({ control, name: 'integration_type' })
  const providerHint = useWatch({ control, name: 'configuration.provider_hint' })
  const [isTypeOpen, setIsTypeOpen] = useState(false)
  const [isProviderOpen, setIsProviderOpen] = useState(false)

  const isLLM = integrationType === IntegrationTypeEnum.LLM_PROVIDER
  const isAAP = integrationType === IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM
  const typeConfig = isLLM
    ? {
        nameLabel: 'Name',
        namePlaceholder: 'Enter provider name',
        showProviderHint: true,
        hideBaseUrl: typeof providerHint === 'string' && PROVIDERS_HIDING_BASE_URL.has(providerHint),
        requireBaseUrl: typeof providerHint === 'string' && PROVIDERS_REQUIRING_BASE_URL.has(providerHint),
        baseUrlPlaceholder: 'https://api.example.com/v1',
      }
    : {
        nameLabel: 'Server name / ID',
        namePlaceholder: 'Enter server name / ID',
        showProviderHint: false,
        hideBaseUrl: false,
        requireBaseUrl: true,
        baseUrlPlaceholder: isAAP ? 'e.g. https://aap.example.com' : 'https://mcp-server.example.com/mcp',
      }

  const renderTypeToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <IntegrationTypeMenuToggle
        toggleRef={toggleRef}
        value={integrationType}
        onClick={() => setIsTypeOpen((prev) => !prev)}
        isExpanded={isTypeOpen}
      />
    ),
    [integrationType, isTypeOpen]
  )

  const renderProviderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <ProviderHintMenuToggle
        toggleRef={toggleRef}
        value={String(providerHint ?? '')}
        onClick={() => setIsProviderOpen((prev) => !prev)}
        isExpanded={isProviderOpen}
      />
    ),
    [providerHint, isProviderOpen]
  )

  return (
    <>
      <Title headingLevel="h2" size="lg" className={styles.stepTitle}>
        Integration details
      </Title>
      <Content component={ContentVariants.p} className={styles.stepDescription}>
        Select an integration type and provide connection details.
      </Content>
      <Form className={styles.stepForm}>
        <FormGroup
          label="Integration type"
          fieldId="integration-type"
          isRequired
          labelHelp={integrationHelp.integrationType}
        >
          <Controller
            name="integration_type"
            control={control}
            render={({ field }) => (
              <IntegrationTypeSelect
                value={field.value}
                isOpen={isTypeOpen}
                onOpenChange={setIsTypeOpen}
                onSelect={(value) => {
                  const validType = INTEGRATION_TYPE_OPTIONS.find((opt) => opt.value === value)
                  if (!validType) return
                  onTypeChange(validType.value)
                  setIsTypeOpen(false)
                }}
                renderToggle={renderTypeToggle}
              />
            )}
          />
        </FormGroup>
        <ControlledTextField
          control={control}
          name="name"
          label={typeConfig.nameLabel}
          fieldId="name"
          placeholder={typeConfig.namePlaceholder}
          isRequired
          labelHelp={isLLM ? integrationHelp.name : integrationHelp.serverName}
        />
        <ControlledTextField
          control={control}
          name="description"
          label="Description"
          fieldId="description"
          placeholder="Enter description"
        />
        {typeConfig.showProviderHint && (
          <FormGroup label="Provider type" fieldId="provider-hint" isRequired labelHelp={integrationHelp.providerType}>
            <Controller
              name="configuration.provider_hint"
              control={control}
              render={({ field }) => (
                <ProviderHintSelect
                  value={field.value as string | undefined}
                  isOpen={isProviderOpen}
                  onOpenChange={setIsProviderOpen}
                  onSelect={(value) => {
                    const validProvider = PROVIDER_HINT_OPTIONS.find((opt) => opt.value === value)
                    if (!validProvider) return
                    field.onChange(validProvider.value)
                    setValue(
                      'configuration.base_url',
                      PROVIDERS_HIDING_BASE_URL.has(validProvider.value) ? undefined : ''
                    )
                    setIsProviderOpen(false)
                  }}
                  renderToggle={renderProviderToggle}
                />
              )}
            />
          </FormGroup>
        )}
        {!typeConfig.hideBaseUrl && (
          <ControlledTextField
            control={control}
            name="configuration.base_url"
            label="API URL"
            fieldId="base-url"
            placeholder={typeConfig.baseUrlPlaceholder}
            isRequired={typeConfig.requireBaseUrl}
            labelHelp={isAAP ? integrationHelp.aapUrl : integrationHelp.apiUrl}
          />
        )}

        <SecurityFields control={control} />

        <ScopeFields
          control={control}
          scope={scope}
          scopeName="scope"
          projectIdsName="project_ids"
          idPrefix="integration"
          onScopeChange={(newScope) => {
            if (newScope === 'global') setValue('project_ids', [])
          }}
        />
      </Form>
    </>
  )
}
