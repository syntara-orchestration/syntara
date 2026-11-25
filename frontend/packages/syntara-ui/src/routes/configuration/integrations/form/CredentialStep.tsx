import { Button, Content, ContentVariants, Form, FormGroup, Title } from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'
import type { ReactElement } from 'react'
import type { UseFormSetValue } from 'react-hook-form'

import { SynFormField } from '../../../../components/forms/SynFormField'
import { CredentialSelector } from '../../../builder/components/CredentialSelector'
import { integrationHelp } from '../integrationFieldHelp'
import { CREDENTIAL_REQUIRED_TYPES, CREDENTIAL_TYPES_BY_INTEGRATION } from '../integrationFilters'

import type { IntegrationFormData } from './integrationFormSchema'
import styles from './WizardSteps.module.css'

type CredentialStepCopy = {
  title: string
  description: string
  fieldLabel: string
  placeholder: string
  labelHelp: ReactElement
}

function getCredentialStepCopy(integrationTypeValue: string): CredentialStepCopy {
  if (integrationTypeValue === IntegrationTypeEnum.LLM_PROVIDER) {
    return {
      title: 'Connection credential',
      description:
        'This credential is used to verify that the LLM provider is reachable and the API key is valid. Workflow credentials are configured separately in the workflow builder.',
      fieldLabel: 'Health check credential',
      placeholder: 'Select a credential',
      labelHelp: integrationHelp.healthCheckCredential,
    }
  }

  if (integrationTypeValue === IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM) {
    return {
      title: 'Connection credential',
      description:
        'This credential is used to verify that the Ansible Automation Platform is reachable and the token is valid. Workflow credentials are configured separately in the workflow builder.',
      fieldLabel: 'Health check credential',
      placeholder: 'Select a credential',
      labelHelp: integrationHelp.healthCheckCredential,
    }
  }

  if (integrationTypeValue === IntegrationTypeEnum.OPENSHIFT) {
    return {
      title: 'Authentication',
      description:
        'Use a service account token to authenticate to the cluster API. Credentials are stored encrypted in the platform credential store.',
      fieldLabel: 'Service account token',
      placeholder: 'Select or create a credential',
      labelHelp: integrationHelp.serviceAccountToken,
    }
  }

  return {
    title: 'Connection credential',
    description:
      'This credential is used to discover resources for this integration. Workflow credentials are configured separately in the workflow builder. Test the connection to discover available resources for this integration.',
    fieldLabel: 'Health check credential',
    placeholder: 'Select a credential',
    labelHelp: integrationHelp.healthCheckCredential,
  }
}

type CredentialStepProps = Readonly<{
  setValue: UseFormSetValue<IntegrationFormData>
  credentialId: string | null | undefined
  integrationTypeValue: string
  isTesting: boolean
  onTestConnection: () => void
  onCredentialChange: () => void
}>

export function CredentialStep({
  setValue,
  credentialId,
  integrationTypeValue,
  isTesting,
  onTestConnection,
  onCredentialChange,
}: CredentialStepProps) {
  const isRequired = CREDENTIAL_REQUIRED_TYPES.has(integrationTypeValue)
  const isTestDisabled = isRequired ? !credentialId || isTesting : isTesting
  const copy = getCredentialStepCopy(integrationTypeValue)

  return (
    <>
      <Title headingLevel="h2" size="lg" className={styles.stepTitle}>
        {copy.title}
      </Title>
      <Content component={ContentVariants.p} className={styles.stepDescription}>
        {copy.description}
      </Content>
      <Form className={styles.stepForm}>
        <SynFormField<IntegrationFormData, 'management_credential_id'>
          name="management_credential_id"
          label={copy.fieldLabel}
          fieldId="credential-select"
          isRequired={isRequired}
          labelHelp={copy.labelHelp}
          hideFormGroupLabel
          hideFooter
        >
          {({ field }) => (
            <CredentialSelector
              value={field.value ?? undefined}
              onChange={(id) => {
                setValue('management_credential_id', id ?? null)
                onCredentialChange()
              }}
              compatibleTypeNames={CREDENTIAL_TYPES_BY_INTEGRATION[integrationTypeValue]}
              label={copy.fieldLabel}
              fieldId="credential-select"
              isRequired={isRequired}
              allowCreate
              placeholder={copy.placeholder}
              labelHelp={copy.labelHelp}
            />
          )}
        </SynFormField>
        <FormGroup fieldId="test-connection">
          <Button
            variant="secondary"
            onClick={isTestDisabled ? undefined : onTestConnection}
            isLoading={isTesting}
            isAriaDisabled={isTestDisabled}
          >
            Test connection
          </Button>
        </FormGroup>
      </Form>
    </>
  )
}
