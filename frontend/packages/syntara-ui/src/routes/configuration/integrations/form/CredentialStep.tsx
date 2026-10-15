import { Button, Content, ContentVariants, Form, FormGroup, Title } from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { Controller, type Control, type UseFormSetValue } from 'react-hook-form'

import { CredentialSelector } from '../../../builder/components/CredentialSelector'
import { integrationHelp } from '../integrationFieldHelp'
import { CREDENTIAL_REQUIRED_TYPES, CREDENTIAL_TYPES_BY_INTEGRATION } from '../integrationFilters'

import type { IntegrationFormData } from './integrationFormSchema'
import styles from './WizardSteps.module.css'

const STEP_DESCRIPTION: Record<string, string> = {
  [IntegrationTypeEnum.MCP_SERVER]:
    'This credential is used to discover resources for this integration. Workflow credentials are configured separately in the workflow builder. Test the connection to discover available resources for this integration.',
  [IntegrationTypeEnum.LLM_PROVIDER]:
    'This credential is used to verify that the LLM provider is reachable and the API key is valid. Workflow credentials are configured separately in the workflow builder.',
  [IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM]:
    'This credential is used to verify that the Ansible Automation Platform is reachable and the token is valid. Workflow credentials are configured separately in the workflow builder.',
  [IntegrationTypeEnum.KAFKA]:
    'This credential is the Kafka-connection login used to verify that the brokers are reachable. Workflow credentials are configured separately in the workflow builder.',
}

type CredentialStepProps = Readonly<{
  control: Control<IntegrationFormData>
  setValue: UseFormSetValue<IntegrationFormData>
  credentialId: string | null | undefined
  integrationTypeValue: string
  isTesting: boolean
  onTestConnection: () => void
  onCredentialChange: () => void
}>

export function CredentialStep({
  control,
  setValue,
  credentialId,
  integrationTypeValue,
  isTesting,
  onTestConnection,
  onCredentialChange,
}: CredentialStepProps) {
  const isRequired = CREDENTIAL_REQUIRED_TYPES.has(integrationTypeValue)
  const isTestDisabled = isRequired ? !credentialId || isTesting : isTesting

  return (
    <>
      <Title headingLevel="h2" size="lg" className={styles.stepTitle}>
        Connection credential
      </Title>
      <Content component={ContentVariants.p} className={styles.stepDescription}>
        {STEP_DESCRIPTION[integrationTypeValue] ?? STEP_DESCRIPTION[IntegrationTypeEnum.MCP_SERVER]}
      </Content>
      <Form className={styles.stepForm}>
        <Controller
          name="management_credential_id"
          control={control}
          render={({ field }) => (
            <CredentialSelector
              value={field.value ?? undefined}
              onChange={(id) => {
                setValue('management_credential_id', id ?? null)
                onCredentialChange()
              }}
              compatibleTypeNames={CREDENTIAL_TYPES_BY_INTEGRATION[integrationTypeValue]}
              label="Health check credential"
              fieldId="credential-select"
              isRequired={isRequired}
              allowCreate
              placeholder="Select a credential"
              labelHelp={integrationHelp.healthCheckCredential}
            />
          )}
        />
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
