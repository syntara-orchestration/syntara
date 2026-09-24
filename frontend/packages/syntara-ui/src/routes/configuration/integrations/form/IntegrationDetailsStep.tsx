import {
  Checkbox,
  Content,
  ContentVariants,
  ExpandableSection,
  Form,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  TextArea,
  Title,
} from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { type ReactNode, type Ref, useCallback, useState } from 'react'
import { useWatch, type UseFormSetValue } from 'react-hook-form'

import { SynFormField } from '../../../../components/forms/SynFormField'
import { SynTextField } from '../../../../components/forms/SynTextField'
import { SynSelect } from '../../../../components/SynSelect'
import { integrationHelp } from '../integrationFieldHelp'
import { PROVIDERS_HIDING_BASE_URL, PROVIDERS_REQUIRING_BASE_URL } from '../integrationFilters'

import { INTEGRATION_TYPE_OPTIONS, PROVIDER_HINT_OPTIONS, type IntegrationFormData } from './integrationFormSchema'
import { ScopeFields } from './ScopeFields'
import styles from './WizardSteps.module.css'

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

function SecurityFields() {
  const [isExpanded, setIsExpanded] = useState(false)
  const skipTlsVerify = useWatch<IntegrationFormData, 'configuration.insecure_skip_tls_verify'>({
    name: 'configuration.insecure_skip_tls_verify',
  })

  return (
    <ExpandableSection
      toggleText="Security"
      isExpanded={isExpanded}
      onToggle={(_e, expanded) => setIsExpanded(expanded)}
      isIndented
    >
      <div className={styles.securityFields}>
        <SynFormField<IntegrationFormData, 'configuration.allow_http'>
          name="configuration.allow_http"
          label="Allow HTTP connections"
          fieldId="allow-http"
          hideFormGroupLabel
          hideFooter
        >
          {({ field }) => (
            <Checkbox
              id="allow-http"
              label="Allow HTTP connections"
              description="Permits unencrypted HTTP URLs for this integration"
              isChecked={field.value}
              onChange={(_event, checked) => field.onChange(checked)}
            />
          )}
        </SynFormField>
        <SynFormField<IntegrationFormData, 'configuration.insecure_skip_tls_verify'>
          name="configuration.insecure_skip_tls_verify"
          label="Disable TLS certificate verification"
          fieldId="insecure-skip-tls-verify"
          hideFormGroupLabel
          hideFooter
        >
          {({ field }) => (
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
        </SynFormField>
        {!skipTlsVerify && (
          <SynFormField<IntegrationFormData, 'configuration.ca_certificate'>
            name="configuration.ca_certificate"
            label="CA certificate"
            fieldId="ca-certificate"
            hint="PEM-encoded CA certificate to trust for this integration's TLS connections."
          >
            {({ field }) => (
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
          </SynFormField>
        )}
      </div>
    </ExpandableSection>
  )
}

type IntegrationDetailsStepProps = Readonly<{
  setValue: UseFormSetValue<IntegrationFormData>
  onTypeChange: (newType: string) => void
}>

export function IntegrationDetailsStep({ setValue, onTypeChange }: IntegrationDetailsStepProps) {
  const scope = useWatch<IntegrationFormData, 'scope'>({ name: 'scope' })
  const integrationType = useWatch<IntegrationFormData, 'integration_type'>({ name: 'integration_type' })
  const providerHint = useWatch<IntegrationFormData, 'configuration.provider_hint'>({
    name: 'configuration.provider_hint',
  })
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
        <SynFormField<IntegrationFormData, 'integration_type'>
          name="integration_type"
          label="Integration type"
          fieldId="integration-type"
          isRequired
          labelHelp={integrationHelp.integrationType}
        >
          {({ field }) => (
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
        </SynFormField>
        <SynTextField<IntegrationFormData, 'name'>
          name="name"
          label={typeConfig.nameLabel}
          fieldId="name"
          placeholder={typeConfig.namePlaceholder}
          isRequired
          labelHelp={isLLM ? integrationHelp.name : integrationHelp.serverName}
        />
        <SynTextField<IntegrationFormData, 'description'>
          name="description"
          label="Description"
          fieldId="description"
          placeholder="Enter description"
        />
        {typeConfig.showProviderHint && (
          <SynFormField<IntegrationFormData, 'configuration.provider_hint'>
            name="configuration.provider_hint"
            label="Provider type"
            fieldId="provider-hint"
            isRequired
            labelHelp={integrationHelp.providerType}
          >
            {({ field }) => (
              <ProviderHintSelect
                value={field.value}
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
          </SynFormField>
        )}
        {!typeConfig.hideBaseUrl && (
          <SynTextField<IntegrationFormData, 'configuration.base_url'>
            name="configuration.base_url"
            label="API URL"
            fieldId="base-url"
            placeholder={typeConfig.baseUrlPlaceholder}
            isRequired={typeConfig.requireBaseUrl}
            labelHelp={isAAP ? integrationHelp.aapUrl : integrationHelp.apiUrl}
          />
        )}

        <SecurityFields />

        <ScopeFields<IntegrationFormData>
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
